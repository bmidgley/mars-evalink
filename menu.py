#!/usr/bin/env python3
"""
Django Development Menu
Provides easy access to common Django commands
"""

import os
import sys
import subprocess
import signal
from pathlib import Path

class DjangoMenu:
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.django_dir = self.project_root / "evalink"
        self.venv_activate = self.project_root / "marsenv" / "bin" / "activate"
        
    def setup_environment(self):
        """Set up environment variables for Django"""
        os.environ.update({
            'HOST': 'localhost',
            'NAME': 'evalink',
            'PORT': '5432',
            'DBUSER': 'evalink',
            'PASSWORD': os.getenv('PASSWORD', 'postgres'),
            'SSLMODE': 'disable',
            'CAMPUS': 'Test Campus',
            'MQTT_SERVER': 'localhost',
            'MQTT_PORT': '1883',
            'MQTT_USER': 'testuser',
            'MQTT_PASSWORD': 'testpass',
            'MQTT_NODE_NUMBER': '12345',
            'MQTT_TLS': '0',
            'MQTT_TOPIC': 'test/topic',
            'DJANGO_SETTINGS_MODULE': 'evalink.settings'
        })
        
    def run_command(self, command, working_dir=None):
        """Run a command in the Django directory"""
        if working_dir is None:
            working_dir = self.django_dir
            
        print(f"\n🔄 Running: {command}")
        print(f"📁 Working directory: {working_dir}")
        print("-" * 50)
        
        try:
            # Activate virtual environment and run command
            if self.venv_activate.exists():
                cmd = f"source {self.venv_activate} && cd {working_dir} && {command}"
                subprocess.run(cmd, shell=True, executable='/bin/bash')
            else:
                subprocess.run(command, shell=True, cwd=working_dir)
        except KeyboardInterrupt:
            print("\n⏹️  Command interrupted by user")
        except Exception as e:
            print(f"❌ Error running command: {e}")
    
    def show_menu(self):
        """Display the main menu"""
        while True:
            print("\n" + "=" * 60)
            print("🚀 Django Development Menu")
            print("=" * 60)
            print("1. 🖥️   Run Development Server (runserver)")
            print("2. 🧪 Run Tests")
            print("3. 🗄️   Run Database Migrations")
            print("4. 📊 Create Database Schema Diagram")
            print("5. 🧹 Collect Static Files")
            print("6. 👤 Create Superuser")
            print("7. 🔍 Django Shell")
            print("8. 📋 Show Django Commands")
            print("9. ⚙️   Check Django Configuration")
            print("0. 🚪 Exit")
            print("-" * 60)
            
            choice = input("Enter your choice (0-9): ").strip()
            
            if choice == '0':
                print("👋 Goodbye!")
                break
            elif choice == '1':
                self.run_runserver()
            elif choice == '2':
                self.run_tests()
            elif choice == '3':
                self.run_migrations()
            elif choice == '4':
                self.create_schema_diagram()
            elif choice == '5':
                self.collect_static()
            elif choice == '6':
                self.create_superuser()
            elif choice == '7':
                self.run_shell()
            elif choice == '8':
                self.show_commands()
            elif choice == '9':
                self.check_configuration()
            else:
                print("❌ Invalid choice. Please try again.")
    
    def run_runserver(self):
        """Run Django development server"""
        print("\n🌐 Starting Django Development Server...")
        print("📱 Server will be available at: http://127.0.0.1:8000/")
        print("⏹️  Press Ctrl+C to stop the server")
        self.run_command("python manage.py runserver")
    
    def run_tests(self):
        """Run Django tests"""
        print("\n🧪 Running Django Tests...")
        self.setup_environment()
        os.environ['DJANGO_SETTINGS_MODULE'] = 'evalink.test_settings'
        self.run_command("python manage.py test --verbosity=2")
    
    def run_migrations(self):
        """Run database migrations"""
        print("\n🗄️  Running Database Migrations...")
        self.run_command("python manage.py migrate")
    
    def create_schema_diagram(self):
        """Create database schema diagram"""
        print("\n📊 Creating Database Schema Diagram...")
        self.run_command("python manage.py graph_models -a -g -o ../docs/schema.png")
    
    def collect_static(self):
        """Collect static files"""
        print("\n🧹 Collecting Static Files...")
        self.run_command("python manage.py collectstatic --noinput")
    
    def create_superuser(self):
        """Create a superuser"""
        print("\n👤 Creating Superuser...")
        self.run_command("python manage.py createsuperuser")
    
    def run_shell(self):
        """Run Django shell"""
        print("\n🔍 Starting Django Shell...")
        self.run_command("python manage.py shell")
    
    def show_commands(self):
        """Show available Django commands"""
        print("\n📋 Available Django Commands:")
        self.run_command("python manage.py help")
    
    def check_configuration(self):
        """Check Django configuration"""
        print("\n⚙️  Checking Django Configuration...")
        self.run_command("python manage.py check")

def main():
    """Main entry point"""
    menu = DjangoMenu()
    
    # Handle Ctrl+C gracefully
    def signal_handler(sig, frame):
        print("\n👋 Goodbye!")
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        menu.show_menu()
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

if __name__ == "__main__":
    main()
