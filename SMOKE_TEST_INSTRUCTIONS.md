# Smoke Test Instructions for Stock Screener Application

## Verifying the Application Starts Correctly

Follow these steps to confirm that the refactored stock screener application starts correctly using the factory pattern:

### Method 1: Using the Entry Point Script (Recommended)
```bash
# Navigate to the project directory
cd C:\Users\91996\Documents\My Projects\stock-screener

# Run the application using the canonical entry point
python run.py
```

### Method 2: Using the Shim (Alternative)
```bash
# Navigate to the project directory  
cd C:\Users\91996\Documents\My Projects\stock-screener

# Run the application using the shim (thin wrapper)
python app.py
```

### Expected Output
When the application starts successfully, you should see output similar to:
```
 * Serving Flask app "app" (lazy loading)
 * Environment: development
 * Debug mode: on
 * Running on http://127.0.0.1:5000/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: xxx-xxx-xxx
```

### Quick Import Test (Alternative)
If you just want to verify the application factory works without starting the server:

```bash
cd C:\Users\91996\Documents\My Projects\stock-screener
python -c "from app import create_app; app = create_app(); print('✅ SUCCESS: Flask app created successfully'); print(f'   App name: {app.import_name}'); print(f'   Blueprints registered: {list(app.blueprints.keys())}')"
```

### Test API Endpoints (After Server Starts)
Once the server is running, you can test key endpoints in another terminal or using curl/postman:

```bash
# Test health/endpoint (if available)
curl http://127.0.0.1:5000/api/v1/screener/scan

# Test screener endpoint
curl http://127.0.0.1:5000/api/v1/screener/stock/AAPL
```

### Troubleshooting
If you encounter issues:

1. **Import Errors**: Ensure you're in the project directory and the virtual environment is activated (if applicable)
2. **Port Already in Use**: Change the port in the command or stop conflicting processes
3. **Database Errors**: Ensure `scan_history.db` exists or the application can create it
4. **Missing Dependencies**: Install requirements with `pip install -r requirements.txt` (if file exists)

### Verification Checklist
✅ Application factory pattern properly implemented  
✅ `app.py` serves as thin wrapper delegating to factory  
✅ `run.py` correctly uses factory pattern  
✅ All service layer files migrated (`app/services/`)  
✅ All API blueprints created (`app/api/v1/`)  
✅ Database helpers migrated to `app/database.py`  
✅ Performance tests created and validated  
✅ Documentation updated to reflect completion  

The application is now ready for use with the refactored architecture!