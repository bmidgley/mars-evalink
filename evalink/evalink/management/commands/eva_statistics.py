from django.core.management.base import BaseCommand
from django.db.models import Q
from evalink.models import *
import os
import math
from collections import defaultdict
from datetime import datetime


class Command(BaseCommand):
    help = 'Generate EVA statistics report and save to /tmp/export2141/'

    def add_arguments(self, parser):
        parser.add_argument(
            '--campus',
            type=str,
            default=os.getenv('CAMPUS', 'default'),
            help='Campus name to generate statistics for'
        )

    def handle(self, *args, **options):
        campus_name = options['campus']
        
        try:
            campus = Campus.objects.get(name=campus_name)
        except Campus.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f'Campus "{campus_name}" not found')
            )
            return

        inner_fence = campus.inner_geofence
        
        if not inner_fence:
            self.stdout.write(
                self.style.ERROR('No inner geofence configured for this campus')
            )
            return

        # Create output directory
        output_dir = '/tmp/export2141'
        os.makedirs(output_dir, exist_ok=True)

        # Get all stations (excluding infrastructure and ignore types)
        stations = Station.objects.exclude(
            Q(station_type='infrastructure') | Q(station_type='ignore')
        ).all()

        # Statistics dictionaries
        stats_by_year = defaultdict(lambda: {'count': 0, 'total_distance': 0.0, 'distances': []})
        stats_by_month = defaultdict(lambda: {'count': 0, 'total_distance': 0.0, 'distances': []})
        total_stats = {'count': 0, 'total_distance': 0.0, 'distances': []}

        def haversine_distance(lat1, lon1, lat2, lon2):
            """Calculate the great circle distance between two points on Earth in kilometers."""
            # Convert latitude and longitude from degrees to radians
            lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
            
            # Haversine formula
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            
            # Radius of earth in kilometers
            r = 6371
            return c * r

        def is_outside_fence(lat, lon):
            """Check if coordinates are outside the inner geofence"""
            return (lat < inner_fence.latitude1 or lat > inner_fence.latitude2 or 
                    lon < inner_fence.longitude1 or lon > inner_fence.longitude2)

        def detect_eva_trips(position_logs):
            """Detect EVA trips from position logs by finding sequences outside the geofence"""
            trips = []
            current_trip = []
            outside_fence = False
            
            for log in position_logs:
                is_outside = is_outside_fence(log.latitude, log.longitude)
                
                if is_outside and not outside_fence:
                    # Starting a new trip outside the fence
                    current_trip = [log]
                    outside_fence = True
                elif is_outside and outside_fence:
                    # Continuing current trip
                    current_trip.append(log)
                elif not is_outside and outside_fence:
                    # Ending current trip
                    if len(current_trip) >= 2:  # Need at least 2 points to calculate distance
                        trips.append(current_trip)
                    current_trip = []
                    outside_fence = False
            
            # Handle case where trip ends while still outside fence
            if outside_fence and len(current_trip) >= 2:
                trips.append(current_trip)
            
            return trips

        def calculate_trip_distance(trip_logs):
            """Calculate total distance for a trip"""
            total_distance = 0.0
            for i in range(1, len(trip_logs)):
                prev_log = trip_logs[i-1]
                curr_log = trip_logs[i]
                distance = haversine_distance(
                    prev_log.latitude, prev_log.longitude,
                    curr_log.latitude, curr_log.longitude
                )
                total_distance += distance
            return total_distance

        # Process each station
        for station in stations:
            # Get all position logs for this station, ordered by time
            position_logs = PositionLog.objects.filter(
                station=station
            ).order_by('updated_at')

            if not position_logs.exists():
                continue

            # Detect EVA trips for this station
            eva_trips = detect_eva_trips(position_logs)

            # Process each detected trip
            for trip in eva_trips:
                if len(trip) < 2:
                    continue
                    
                trip_distance = calculate_trip_distance(trip)

                # Use the first log's timestamp for year/month classification
                first_log = trip[0]
                trip_date = first_log.updated_at
                year = trip_date.year
                month_key = f"{year}-{trip_date.month:02d}"

                # Update statistics
                stats_by_year[year]['count'] += 1
                stats_by_year[year]['total_distance'] += trip_distance
                stats_by_year[year]['distances'].append(trip_distance)

                stats_by_month[month_key]['count'] += 1
                stats_by_month[month_key]['total_distance'] += trip_distance
                stats_by_month[month_key]['distances'].append(trip_distance)

                total_stats['count'] += 1
                total_stats['total_distance'] += trip_distance
                total_stats['distances'].append(trip_distance)

        # Calculate averages
        for year_data in stats_by_year.values():
            if year_data['count'] > 0:
                year_data['average_distance'] = year_data['total_distance'] / year_data['count']
            else:
                year_data['average_distance'] = 0.0

        for month_data in stats_by_month.values():
            if month_data['count'] > 0:
                month_data['average_distance'] = month_data['total_distance'] / month_data['count']
            else:
                month_data['average_distance'] = 0.0

        if total_stats['count'] > 0:
            total_stats['average_distance'] = total_stats['total_distance'] / total_stats['count']
        else:
            total_stats['average_distance'] = 0.0

        # Sort data for display
        sorted_years = sorted(stats_by_year.items())
        sorted_months = sorted(stats_by_month.items())

        # Generate standalone HTML content with inline CSS
        html_content = self.generate_html_content(
            total_stats, sorted_years, sorted_months, campus_name
        )

        # Write standalone HTML file
        html_file = os.path.join(output_dir, 'eva_statistics.html')

        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)

        self.stdout.write(
            self.style.SUCCESS(f'EVA statistics report generated successfully!')
        )
        self.stdout.write(f'Standalone HTML file: {html_file}')
        self.stdout.write(f'Total EVAs: {total_stats["count"]}')
        self.stdout.write(f'Total Distance: {total_stats["total_distance"]:.2f} km')

    def generate_html_content(self, total_stats, sorted_years, sorted_months, campus_name):
        """Generate HTML content for the report"""
        html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>EVA Statistics - {campus_name}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            line-height: 1.6;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}

        h1 {{
            color: #333;
            text-align: center;
            margin-bottom: 10px;
        }}

        .generated-info {{
            text-align: center;
            color: #666;
            font-style: italic;
            margin-bottom: 30px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}

        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}

        th {{
            background-color: #f8f9fa;
            font-weight: bold;
            color: #333;
        }}

        tr:nth-child(even) {{
            background-color: #f9f9f9;
        }}

        tr:hover {{
            background-color: #f5f5f5;
        }}

        .number {{
            text-align: right;
        }}

        .summary {{
            background-color: #e3f2fd;
            border-left: 4px solid #2196f3;
            padding: 15px;
            margin: 20px 0;
        }}

        .section {{
            margin: 30px 0;
        }}

        .section h2 {{
            color: #1976d2;
            border-bottom: 2px solid #1976d2;
            padding-bottom: 10px;
        }}

        @media print {{
            body {{
                background-color: white;
                margin: 0;
            }}
            
            .container {{
                box-shadow: none;
                border-radius: 0;
            }}
            
            tr:hover {{
                background-color: transparent;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>EVA Statistics - {campus_name}</h1>
        <p class="generated-info">Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
        
        <!-- Summary Section -->
        <div class="summary">
            <h2>Summary</h2>
            <p><strong>Total EVAs:</strong> {total_stats['count']}</p>
            <p><strong>Total Distance:</strong> {total_stats['total_distance']:.2f} km</p>
            <p><strong>Average Distance per EVA:</strong> {total_stats['average_distance']:.2f} km</p>
        </div>

        <!-- Statistics by Year -->
        <div class="section">
            <h2>Statistics by Year</h2>'''
        
        if sorted_years:
            html += '''
            <table>
                <thead>
                    <tr>
                        <th>Year</th>
                        <th class="number">Number of EVAs</th>
                        <th class="number">Total Distance (km)</th>
                        <th class="number">Average Distance (km)</th>
                    </tr>
                </thead>
                <tbody>'''
            
            for year, data in sorted_years:
                html += f'''
                    <tr>
                        <td>{year}</td>
                        <td class="number">{data['count']}</td>
                        <td class="number">{data['total_distance']:.2f}</td>
                        <td class="number">{data['average_distance']:.2f}</td>
                    </tr>'''
            
            html += '''
                </tbody>
            </table>'''
        else:
            html += '<p>No EVA data available by year.</p>'
        
        html += '''
        </div>

        <!-- Statistics by Month -->
        <div class="section">
            <h2>Statistics by Month</h2>'''
        
        if sorted_months:
            html += '''
            <table>
                <thead>
                    <tr>
                        <th>Month</th>
                        <th class="number">Number of EVAs</th>
                        <th class="number">Total Distance (km)</th>
                        <th class="number">Average Distance (km)</th>
                    </tr>
                </thead>
                <tbody>'''
            
            for month_key, data in sorted_months:
                html += f'''
                    <tr>
                        <td>{month_key}</td>
                        <td class="number">{data['count']}</td>
                        <td class="number">{data['total_distance']:.2f}</td>
                        <td class="number">{data['average_distance']:.2f}</td>
                    </tr>'''
            
            html += '''
                </tbody>
            </table>'''
        else:
            html += '<p>No EVA data available by month.</p>'
        
        html += '''
        </div>
    </div>
</body>
</html>'''
        
        return html
