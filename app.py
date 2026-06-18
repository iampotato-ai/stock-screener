from app import create_app

# Thin compatibility shim delegating to the application factory pattern
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)