@echo off
echo Running Alert Service Tests...
python test_alert_service.py
echo.
echo Running Alert API Tests...
python test_alerts_api.py
echo.
echo All tests completed!