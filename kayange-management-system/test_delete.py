from app import create_app
import json

app = create_app()

with app.test_client() as client:
    # Login
    resp = client.post('/auth/api/login', json={'username': 'admin', 'password': 'admin123'})
    print('Login:', resp.status_code)
    
    # Get patient list
    resp = client.get('/patients/api')
    data = json.loads(resp.data)
    print('Patients before:', len(data))
    if data:
        patient_id = data[0]['id']
        print('Deleting patient', patient_id, data[0]['first_name'], data[0]['last_name'])
        
        # Delete patient
        resp = client.delete('/patients/api/' + str(patient_id))
        print('Delete status:', resp.status_code)
        print('Delete response:', json.loads(resp.data))
        
        # Check patient list again
        resp = client.get('/patients/api')
        data = json.loads(resp.data)
        print('Patients after:', len(data))
        
        # Check dashboard
        resp = client.get('/reports/api/dashboard')
        data = json.loads(resp.data)
        print('Dashboard total_patients:', data.get('total_patients'))