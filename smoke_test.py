#!/usr/bin/env python3
"""
Smoke test to verify the Flask app can be created successfully.
"""
try:
    from app import create_app
    app = create_app()
    print("✅ SUCCESS: Flask app created successfully")
    print(f"   App name: {app.import_name}")
    print(f"   Debug mode: {app.debug}")
    print(f"   Template folder: {app.template_folder}")
    print(f"   Static folder: {app.static_folder}")

    # Test that blueprints are registered
    blueprint_names = [bp.name for bp in app.blueprints.values()]
    print(f"   Registered blueprints: {blueprint_names}")

    print("\n🎉 Smoke test passed - application factory is working correctly!")

except Exception as e:
    print(f"❌ ERROR: Failed to create Flask app: {e}")
    import traceback
    traceback.print_exc()