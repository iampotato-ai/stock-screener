import os
import sys
import time

os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["SCHEDULER_FORCE_START"] = "true"

print("==================================================")
print("  MomentumScan Stock Screener (NSE India)")
print("==================================================")
print("[1/2] Loading Flask application & ML models...")
sys.stdout.flush()

t0 = time.time()
from app import create_app

env = os.environ.get('FLASK_ENV', 'development')
app = create_app(env)

t_elapsed = round(time.time() - t0, 1)
print(f"[2/2] Application ready in {t_elapsed}s!")

if __name__ == '__main__':
    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    
    print("--------------------------------------------------")
    print(f"  Live Server running at: http://{host}:{port}")
    print("  Open http://127.0.0.1:5000 in your web browser.")
    print("==================================================")
    sys.stdout.flush()
    
    app.run(host=host, port=port, debug=debug, use_reloader=False)