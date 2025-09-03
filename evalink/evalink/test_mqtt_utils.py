"""
MQTT testing utilities for mocking MQTT connections in tests
"""

from unittest.mock import Mock, patch
import json

class MockMQTTClient:
    """Mock MQTT client for testing"""
    
    def __init__(self):
        self.published_messages = []
        self.subscribed_topics = []
        self.connected = False
        self.disconnected = False
    
    def connect(self, host, port, keepalive):
        self.connected = True
        return 0
    
    def disconnect(self):
        self.disconnected = True
    
    def publish(self, topic, payload, **kwargs):
        self.published_messages.append({
            'topic': topic,
            'payload': payload,
            'kwargs': kwargs
        })
        return (0, 1)  # (result, mid)
    
    def subscribe(self, topic, **kwargs):
        self.subscribed_topics.append(topic)
        return (0, 1)  # (result, mid)
    
    def username_pw_set(self, username, password):
        self.username = username
        self.password = password
    
    def tls_set(self):
        self.tls_enabled = True
    
    def loop_start(self):
        pass
    
    def loop_stop(self):
        pass

def mock_mqtt_client():
    """Decorator to mock MQTT client in tests"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with patch('paho.mqtt.client.Client') as mock_client_class:
                mock_client = MockMQTTClient()
                mock_client_class.return_value = mock_client
                return func(*args, **kwargs)
        return wrapper
    return decorator

def create_test_mqtt_message(message_type, payload, from_node=12345, channel=0):
    """Create a test MQTT message"""
    import time
    return {
        'type': message_type,
        'payload': payload,
        'from': from_node,
        'channel': channel,
        'timestamp': int(time.time()),
        'id': int(time.time() * 1000)
    }
