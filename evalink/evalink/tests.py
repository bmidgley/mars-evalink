from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta
import json
import os
from unittest.mock import patch
from .models import Campus, Station, Hardware, Geofence, StationProfile
from .test_mqtt_utils import mock_mqtt_client, create_test_mqtt_message


class FeaturesEndpointTestCase(TestCase):
    def setUp(self):
        """Set up test data for features endpoint tests"""
        self.client = Client()
        
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        
        # Create test campus
        self.campus = Campus.objects.create(
            name='Test Campus',
            latitude=40.0,
            longitude=-105.0,
            time_zone='America/Denver'
        )
        
        # Create test geofence
        self.geofence = Geofence.objects.create(
            latitude1=39.9,
            longitude1=-105.1,
            latitude2=40.1,
            longitude2=-104.9
        )
        self.campus.inner_geofence = self.geofence
        self.campus.save()
        
        # Create test hardware
        self.hardware = Hardware.objects.create(
            name='Test Hardware',
            hardware_type=1,
            station_type='test'
        )
        
        # Create test station profile
        self.station_profile = StationProfile.objects.create(
            name='Test Profile',
            configuration={},
            compatible_firmwares=['1.0.0']
        )
        
        # Create test stations
        self.station1 = Station.objects.create(
            name='Test Station 1',
            short_name='TS1',
            hardware=self.hardware,
            hardware_node='node1',
            hardware_number=12345,
            station_type='active',
            station_profile=self.station_profile,
            features={
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [-105.0, 40.0]
                },
                'properties': {
                    'name': 'Test Station 1'
                }
            },
            updated_at=timezone.now()
        )
        
        self.station2 = Station.objects.create(
            name='Test Station 2',
            short_name='TS2',
            hardware=self.hardware,
            hardware_node='node2',
            hardware_number=12346,
            station_type='ignore',
            station_profile=self.station_profile,
            features={
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [-105.05, 40.05]
                },
                'properties': {
                    'name': 'Test Station 2'
                }
            },
            updated_at=timezone.now() - timedelta(days=35)  # Old station
        )
        
        # Create full-history group
        self.full_history_group = Group.objects.create(name='full-history')

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_with_authentication(self):
        """Test that authenticated users can access features.json"""
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        
        # Parse response data
        data = json.loads(response.content)
        
        # Assert response structure
        self.assertIn('type', data)
        self.assertEqual(data['type'], 'FeatureCollection')
        self.assertIn('features', data)
        self.assertIsInstance(data['features'], list)
        
        # Assert that only recent stations are included (not the old one)
        self.assertEqual(len(data['features']), 1)
        
        # Assert station data
        feature = data['features'][0]
        self.assertIn('type', feature)
        self.assertEqual(feature['type'], 'Feature')
        self.assertIn('geometry', feature)
        self.assertIn('properties', feature)
        
        # Assert properties
        properties = feature['properties']
        self.assertIn('hardware_number', properties)
        self.assertIn('hardware_node', properties)
        self.assertIn('id', properties)
        self.assertIn('days_old', properties)
        self.assertIn('hours_old', properties)
        self.assertIn('distance', properties)
        
        # Assert distance calculation (should be 0 for station inside geofence)
        self.assertEqual(properties['distance'], 0)

    def test_features_endpoint_without_authentication(self):
        """Test that unauthenticated users are redirected to login"""
        # Make request without authentication
        response = self.client.get('/features.json')
        
        # Assert redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_with_full_history_permission(self):
        """Test that users with full-history permission see all stations"""
        # Add user to full-history group
        self.user.groups.add(self.full_history_group)
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        
        # Parse response data
        data = json.loads(response.content)
        
        # Assert that both stations are included (including old one)
        self.assertEqual(len(data['features']), 2)

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_station_outside_geofence(self):
        """Test distance calculation for stations outside geofence"""
        # Create station outside geofence
        station_outside = Station.objects.create(
            name='Outside Station',
            short_name='OS',
            hardware=self.hardware,
            hardware_node='node3',
            hardware_number=12347,
            station_type='active',
            station_profile=self.station_profile,
            features={
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [-106.0, 41.0]  # Outside geofence
                },
                'properties': {
                    'name': 'Outside Station'
                }
            },
            updated_at=timezone.now()
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        
        # Parse response data
        data = json.loads(response.content)
        
        # Find the outside station
        outside_feature = None
        for feature in data['features']:
            if feature['properties'].get('name') == 'Outside Station':
                outside_feature = feature
                break
        
        # Assert distance calculation (should be 1 for station outside geofence)
        self.assertIsNotNone(outside_feature)
        self.assertEqual(outside_feature['properties']['distance'], 1)

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_station_without_coordinates(self):
        """Test that stations without valid coordinates are excluded"""
        # Create station with invalid coordinates
        station_invalid = Station.objects.create(
            name='Invalid Station',
            short_name='IS',
            hardware=self.hardware,
            hardware_node='node4',
            hardware_number=12348,
            station_type='active',
            station_profile=self.station_profile,
            features={
                'type': 'Feature',
                'geometry': {
                    'type': 'Point',
                    'coordinates': [0, 0]  # Invalid coordinates
                },
                'properties': {
                    'name': 'Invalid Station'
                }
            },
            updated_at=timezone.now()
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        
        # Parse response data
        data = json.loads(response.content)
        
        # Assert that invalid station is not included
        station_names = [f['properties'].get('name') for f in data['features']]
        self.assertNotIn('Invalid Station', station_names)

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_station_without_features(self):
        """Test that stations without features are excluded"""
        # Create station without features
        station_no_features = Station.objects.create(
            name='No Features Station',
            short_name='NFS',
            hardware=self.hardware,
            hardware_node='node5',
            hardware_number=12349,
            station_type='active',
            station_profile=self.station_profile,
            features=None,
            updated_at=timezone.now()
        )
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        
        # Parse response data
        data = json.loads(response.content)
        
        # Assert that station without features is not included
        station_names = [f['properties'].get('name') for f in data['features']]
        self.assertNotIn('No Features Station', station_names)

    @patch.dict(os.environ, {'CAMPUS': 'Test Campus'})
    def test_features_endpoint_campus_without_geofence(self):
        """Test behavior when campus has no geofence"""
        # Remove geofence from campus
        self.campus.inner_geofence = None
        self.campus.save()
        
        # Login user
        self.client.login(username='testuser', password='testpass123')
        
        # Make request to features endpoint
        response = self.client.get('/features.json')
        
        # Assert response
        self.assertEqual(response.status_code, 200)
        
        # Parse response data
        data = json.loads(response.content)
        
        # Assert that features are still returned (without distance calculation)
        self.assertGreater(len(data['features']), 0)
        
        # Check that distance is not calculated when no geofence exists
        feature = data['features'][0]
        self.assertNotIn('distance', feature['properties'])

    def test_features_endpoint_invalid_campus(self):
        """Test behavior when CAMPUS environment variable doesn't match any campus"""
        # Set invalid campus name
        with patch.dict(os.environ, {'CAMPUS': 'Non-existent Campus'}):
            # Login user
            self.client.login(username='testuser', password='testpass123')
            
            # Make request to features endpoint - should raise Campus.DoesNotExist
            with self.assertRaises(Exception) as context:
                response = self.client.get('/features.json')
            
            # Verify the exception is Campus.DoesNotExist
            self.assertIn('Campus matching query does not exist', str(context.exception))

    @mock_mqtt_client()
    def test_mqtt_functionality_with_mock(self):
        """Test that MQTT functionality works with mocked client"""
        # This test demonstrates how to test MQTT-dependent code
        # The @mock_mqtt_client decorator ensures no real MQTT connections are made
        
        # Test that we can create MQTT messages
        test_message = create_test_mqtt_message(
            message_type='text',
            payload={'text': 'Hello from test'},
            from_node=12345
        )
        
        # Verify message structure
        self.assertIn('type', test_message)
        self.assertIn('payload', test_message)
        self.assertIn('from', test_message)
        self.assertIn('timestamp', test_message)
        self.assertEqual(test_message['type'], 'text')
        self.assertEqual(test_message['from'], 12345)
