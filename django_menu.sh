#!/bin/bash

# Django Development Menu Script
# Simple shell-based menu for Django commands

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DJANGO_DIR="$PROJECT_ROOT/evalink"
VENV_ACTIVATE="$PROJECT_ROOT/marsenv/bin/activate"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to run Django command
run_django_command() {
    local command="$1"
    local description="$2"
    
    echo -e "\n${BLUE}🔄 Running: $description${NC}"
    echo -e "${YELLOW}📁 Working directory: $DJANGO_DIR${NC}"
    echo "----------------------------------------"
    
    if [ -f "$VENV_ACTIVATE" ]; then
        source "$VENV_ACTIVATE"
    fi
    
    cd "$DJANGO_DIR"
    eval "$command"
}

# Function to show menu
show_menu() {
    while true; do
        echo -e "\n${GREEN}============================================================${NC}"
        echo -e "${GREEN}🚀 Django Development Menu${NC}"
        echo -e "${GREEN}============================================================${NC}"
        echo "1. 🖥️   Run Development Server (runserver)"
        echo "2. 🧪 Run Tests"
        echo "3. 🗄️   Run Database Migrations"
        echo "4. 📊 Create Database Schema Diagram"
        echo "5. 🧹 Collect Static Files"
        echo "6. 👤 Create Superuser"
        echo "7. 🔍 Django Shell"
        echo "8. 📋 Show Django Commands"
        echo "9. ⚙️   Check Django Configuration"
        echo "0. 🚪 Exit"
        echo -e "${YELLOW}------------------------------------------------------------${NC}"
        
        read -p "Enter your choice (0-9): " choice
        
        case $choice in
            0)
                echo -e "${GREEN}👋 Goodbye!${NC}"
                break
                ;;
            1)
                echo -e "\n${BLUE}🌐 Starting Django Development Server...${NC}"
                echo -e "${YELLOW}📱 Server will be available at: http://127.0.0.1:8000/${NC}"
                echo -e "${YELLOW}⏹️  Press Ctrl+C to stop the server${NC}"
                run_django_command "python manage.py runserver" "Django Development Server"
                ;;
            2)
                echo -e "\n${BLUE}🧪 Running Django Tests...${NC}"
                export DJANGO_SETTINGS_MODULE=evalink.test_settings
                run_django_command "python manage.py test --verbosity=2" "Django Tests"
                ;;
            3)
                echo -e "\n${BLUE}🗄️  Running Database Migrations...${NC}"
                run_django_command "python manage.py migrate" "Database Migrations"
                ;;
            4)
                echo -e "\n${BLUE}📊 Creating Database Schema Diagram...${NC}"
                run_django_command "python manage.py graph_models -a -g -o ../docs/schema.png" "Schema Diagram"
                ;;
            5)
                echo -e "\n${BLUE}🧹 Collecting Static Files...${NC}"
                run_django_command "python manage.py collectstatic --noinput" "Collect Static Files"
                ;;
            6)
                echo -e "\n${BLUE}👤 Creating Superuser...${NC}"
                run_django_command "python manage.py createsuperuser" "Create Superuser"
                ;;
            7)
                echo -e "\n${BLUE}🔍 Starting Django Shell...${NC}"
                run_django_command "python manage.py shell" "Django Shell"
                ;;
            8)
                echo -e "\n${BLUE}📋 Available Django Commands:${NC}"
                run_django_command "python manage.py help" "Django Help"
                ;;
            9)
                echo -e "\n${BLUE}⚙️  Checking Django Configuration...${NC}"
                run_django_command "python manage.py check" "Configuration Check"
                ;;
            *)
                echo -e "${RED}❌ Invalid choice. Please try again.${NC}"
                ;;
        esac
        
        echo -e "\n${YELLOW}Press Enter to continue...${NC}"
        read
    done
}

# Main execution
echo -e "${GREEN}Welcome to Django Development Menu!${NC}"
show_menu
