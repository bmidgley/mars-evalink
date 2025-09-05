# Cursor/VS Code Configuration

This directory contains configuration files for Cursor (and VS Code) to properly work with the Django project and virtual environment.

## Configuration Files

### `settings.json`
- **Python Interpreter**: Configured to use the virtual environment at `../marsenv/bin/python`
- **Environment Activation**: Automatically activates the virtual environment in terminals
- **Linting**: Enabled flake8 for code quality
- **Formatting**: Configured to use Black for code formatting
- **Testing**: Configured for Django's unittest framework
- **File Exclusions**: Hides `__pycache__` directories and `.pyc` files

### `launch.json`
- **Django Server**: Debug configuration to run the Django development server
- **Django Tests**: Debug configuration to run the test suite
- Both configurations use the virtual environment Python interpreter

### `tasks.json`
- **Run Django Server**: Task to start the development server
- **Run Tests**: Task to execute the test suite
- **Make Migrations**: Task to create new database migrations
- **Migrate**: Task to apply database migrations

## Usage

### Selecting Python Interpreter
1. Open Cursor/VS Code in the `evalink` directory
2. Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
3. Type "Python: Select Interpreter"
4. Choose the interpreter at `../marsenv/bin/python`

### Running Tasks
1. Press `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
2. Type "Tasks: Run Task"
3. Select the desired task (Run Django Server, Run Tests, etc.)

### Debugging
1. Set breakpoints in your code
2. Press `F5` or go to Run and Debug panel
3. Select "Django" or "Django Tests" configuration
4. Start debugging

## Virtual Environment

The project uses a virtual environment located at `../marsenv/`. Make sure to:

1. Activate the virtual environment: `source ../marsenv/bin/activate`
2. Install dependencies: `pip install -r ../requirements.txt`
3. Run migrations: `python manage.py migrate`

## Environment Variables

The project uses a `.env` file in the parent directory (`../.env`) for environment variables. Make sure this file exists and contains the necessary configuration for your environment.
