from flask import Flask, render_template, request, jsonify
import json
import base64
import utils
app = Flask(__name__)
PORT = 5000

@app.route('/')
def index():
    return render_template("index.html")

@app.route('/myqr.html')
def findqr():
    return render_template("myqr.html")

@app.route('/get-today-logins', methods=['GET'])
def get_today_logins():
    try:
        # Get today's logins from the utils module
        today_logins = utils.get_today_logins()
        return jsonify({'success': True, 'logins': today_logins}), 200
    except Exception as e:
        print(f"[Ledger] Error getting today's logins: {str(e)}")
        return jsonify({'success': False, 'message': 'Error getting today\'s logins'}), 500

@app.route('/get-qr', methods=['POST'])
def getqr():
    try:
        data = request.get_json()
        uuid = data.get('data','')
        image_data = None
        with open(f"static/QRs/{uuid}.png", "rb") as image_file:
            image_data = image_file.read()
            image_data = base64.b64encode(image_data)
            image_data = image_data.decode('utf-8')
        return jsonify({'success': True, 'message': image_data})
        
    except Exception as e:
        print(e)
        return jsonify({'success': False, 'message': 'Error getting image'})


@app.route('/login', methods=['POST'])
def login():
    print("-" * 50)
    try:
        data = request.get_json()
        uuid = data.get('data', '')

        camper_name = utils.get_name_from_ID(uuid)
        if camper_name is not None:
            # Check current login status and perform login/logout
            action = utils.login_user(uuid)
            
            print(f"[Ledger] ID: {uuid}")
            print(f"[Ledger] {action.title()}: {camper_name}")
            
            action_message = f"{camper_name} has been {'logged in' if action == 'login' else 'logged out'} successfully!"
            
            return jsonify({
                'success': True, 
                'message': action_message, 
                'name': camper_name,
                'action': action
            }), 200
        else:
            print("[Ledger] No matching data found for the scanned QR code.")
        
        return jsonify({'success': False, 'message': 'Data not found', 'name': 'N/A'}), 404
    
    except Exception as e:
        print(f"[Ledger] Error processing QR data: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing data'}), 500
    
@app.route('/qr-data', methods=['POST'])
def receive_qr_data():
    try:
        data = request.get_json()
        uuid = data.get('data', '')
        
        # Print the scanned QR code data to console
        print("-" * 50)
        print(f"[QR SCANNER] Received QR code data: {uuid}")

        camper_name = utils.get_name_from_ID(uuid)
        if camper_name is not None:
            # Check if camper is currently logged in
            is_logged_in = utils.is_camper_logged_in(uuid)
            status = "Currently logged in" if is_logged_in else "Currently logged out"
            
            print(f"[QR SCANNER] Name: {camper_name}")
            print(f"[QR SCANNER] Status: {status}")
            
            return jsonify({
                'success': True, 
                'message': 'Data received successfully', 
                'name': camper_name,
                'is_logged_in': is_logged_in,
                'status': status
            }), 200
        else:
            print("[QR SCANNER] No matching data found for the scanned QR code.")
        
        return jsonify({'success': False, 'message': 'Data not found', 'name': 'N/A'}), 404
    
    except Exception as e:
        print(f"[QR SCANNER] Error processing QR data: {str(e)}")
        return jsonify({'success': False, 'message': 'Error processing data'}), 500
    
@app.route('/get-names', methods=['GET'])
def get_names():
    try:
        return jsonify({'success': True, 'names': utils.get_full_names()}), 200
    
    except Exception as e:
        return jsonify({'success': False, 'message': 'Error getting names'}), 500

if __name__ == '__main__':
    print("Generating QR codes...")
    utils.generate_QRs()
    print("Adding names to images...")
    utils.add_names_to_all_images()

    print("Starting Web Server...")
    print(f"Open your browser and go to: http://localhost:{PORT}")
    print("Make sure to allow camera permissions when prompted!")
    print("-" * 50)
    
    app.run(host='0.0.0.0', port=PORT, debug=True)

