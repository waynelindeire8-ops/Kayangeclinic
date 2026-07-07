import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'kayange.db')

from app.database import init_db, get_db


def seed():
    for f in os.listdir(BASE_DIR):
        if f.startswith('kayange.db'):
            os.remove(os.path.join(BASE_DIR, f))
    init_db()

    db = get_db()
    db.execute("PRAGMA foreign_keys = ON")

    db.execute('DELETE FROM audit_logs')
    db.execute('DELETE FROM departments')
    db.execute('DELETE FROM diet_support')
    db.execute('DELETE FROM referrals')
    db.execute('DELETE FROM pharmacy_dispensing')
    db.execute('DELETE FROM pharmacy_inventory')
    db.execute('DELETE FROM billing_items')
    db.execute('DELETE FROM billing')
    db.execute('DELETE FROM package_services')
    db.execute('DELETE FROM packages')
    db.execute('DELETE FROM medical_certificates')
    db.execute('DELETE FROM procedures')
    db.execute('DELETE FROM lab_tests')
    db.execute('DELETE FROM consultations')
    db.execute('DELETE FROM appointments')
    db.execute('DELETE FROM patient_medications')
    db.execute('DELETE FROM patient_medical_history')
    db.execute('DELETE FROM patient_allergies')
    db.execute('DELETE FROM patients')
    db.execute('DELETE FROM users')

    users = [
        ('admin', generate_password_hash('admin123'), 'admin', 'System', 'Admin', 'admin@kayange.com', '0700000000'),
        ('dr.main', generate_password_hash('doctor123'), 'doctor', 'James', 'Kamau', 'dr.kamau@kayange.com', '0700000001'),
        ('dr.locum1', generate_password_hash('doctor123'), 'locum_doctor', 'Sarah', 'Wanjiku', 'dr.wanjiku@kayange.com', '0700000002'),
        ('dr.locum2', generate_password_hash('doctor123'), 'locum_doctor', 'Peter', 'Omondi', 'dr.omondi@kayange.com', '0700000003'),
        ('dr.locum3', generate_password_hash('doctor123'), 'locum_doctor', 'Grace', 'Muthoni', 'dr.muthoni@kayange.com', '0700000004'),
        ('nurse.main', generate_password_hash('nurse123'), 'nurse', 'Mary', 'Njoki', 'nurse.njoki@kayange.com', '0700000005'),
        ('nurse.locum', generate_password_hash('nurse123'), 'locum_nurse', 'John', 'Kiprop', 'nurse.kiprop@kayange.com', '0700000006'),
        ('lab.tech1', generate_password_hash('lab123'), 'lab_staff', 'Agnes', 'Chebet', 'lab.chebet@kayange.com', '0700000007'),
        ('lab.tech2', generate_password_hash('lab123'), 'lab_staff', 'David', 'Mwangi', 'lab.mwangi@kayange.com', '0700000008'),
        ('front.desk1', generate_password_hash('front123'), 'front_desk', 'Jane', 'Wanjeri', 'front.wanjeri@kayange.com', '0700000009'),
        ('front.desk2', generate_password_hash('front123'), 'front_desk', 'Paul', 'Njoroge', 'front.njoroge@kayange.com', '0700000010'),
        ('file.mgr1', generate_password_hash('file123'), 'file_manager', 'Lucy', 'Akinyi', 'file.akinyi@kayange.com', '0700000011'),
        ('file.mgr2', generate_password_hash('file123'), 'file_manager', 'Tom', 'Odhiambo', 'file.odhiambo@kayange.com', '0700000012'),
    ]

    for u in users:
        db.execute(
            'INSERT INTO users (username, password_hash, role, first_name, last_name, email, phone) VALUES (?,?,?,?,?,?,?)', u)

    departments = [
        ('General Medicine', 'General medical consultations and checkups'),
        ('Internal Medicine', 'Management of chronic diseases and complex internal conditions'),
        ('Pediatrics', 'Medical care for infants, children, and adolescents'),
        ('Maternity', 'Antenatal, delivery, and postnatal care'),
        ('Accident & Emergency', 'Emergency medical care for acute conditions and injuries'),
        ('Radiology', 'X-ray, ultrasound, and other imaging services'),
        ('Laboratory', 'Clinical lab tests and diagnostics'),
        ('Pharmacy', 'Dispensing of medications and pharmaceutical services'),
        ('Outpatient Services', 'Walk-in consultations and minor procedures'),
    ]
    for dept in departments:
        db.execute('INSERT INTO departments (name, description) VALUES (?,?)', dept)

    patients_data = [
        ('KMC-1001', 'Alice', 'Wanjiku', '1990-05-15', 'Female', '0712345678', 'alice@email.com', '123 Nairobi', 'Bob Wanjiku', '0798765432', 'A+', 'NHIF', 'Super Cover'),
        ('KMC-1002', 'Ben', 'Kiprop', '1985-08-22', 'Male', '0723456789', 'ben@email.com', '456 Mombasa Rd', 'Jane Kiprop', '0787654321', 'O+', '', ''),
        ('KMC-1003', 'Carol', 'Nyambura', '2000-01-10', 'Female', '0734567890', 'carol@email.com', '789 Kisumu', 'Peter Nyambura', '0776543210', 'B+', 'AAR', 'Classic'),
        ('KMC-1004', 'David', 'Ochieng', '1978-11-30', 'Male', '0745678901', 'david@email.com', '321 Eldoret', 'Mary Ochieng', '0765432109', 'AB-', '', ''),
        ('KMC-1005', 'Esther', 'Wambui', '1995-03-25', 'Female', '0756789012', 'esther@email.com', '654 Nakuru', 'Samuel Wambui', '0754321098', 'A-', 'NHIF', 'Lite'),
        ('KMC-1006', 'Frank', 'Njenga', '1982-07-14', 'Male', '0767890123', 'frank@email.com', '987 Thika', 'Grace Njenga', '0743210987', 'O-', 'Jubilee', 'Gold'),
        ('KMC-1007', 'Grace', 'Akoth', '1998-12-05', 'Female', '0778901234', 'grace@email.com', '111 Machakos', 'John Akoth', '0732109876', 'AB+', '', ''),
        ('KMC-1008', 'Henry', 'Kariuki', '1975-09-18', 'Male', '0789012345', 'henry@email.com', '222 Meru', 'Lucy Kariuki', '0721098765', 'B-', 'NHIF', 'Super Cover'),
    ]

    for p in patients_data:
        db.execute(
            '''INSERT INTO patients (patient_id, first_name, last_name, dob, gender, phone, email, address,
               emergency_contact_name, emergency_contact_phone, blood_group, scheme_provider, scheme_type)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', p)

    for pid in range(1, 9):
        allergies_list = [
            ['Penicillin'], ['Aspirin'], ['None'], ['Sulfa'], ['Latex'], ['Penicillin', 'Ibuprofen'], ['None'], ['Codeine']
        ]
        for allergy in allergies_list[pid - 1]:
            db.execute('INSERT INTO patient_allergies (patient_id, allergy) VALUES (?,?)', (pid, allergy))

        medical_history_list = [
            [('Hypertension', '2020-01-01', 'On medication')],
            [('Diabetes Type 2', '2019-06-15', 'Diet controlled')],
            [('Asthma', '2010-03-20', 'Uses inhaler as needed')],
            [('Arthritis', '2021-09-10', '')],
            [('None', None, '')],
            [('Heart Disease', '2018-11-01', 'Regular checkups')],
            [('Migraine', '2022-02-14', '')],
            [('None', None, '')],
        ]
        for cond in medical_history_list[pid - 1]:
            if cond[0] != 'None':
                db.execute('INSERT INTO patient_medical_history (patient_id, condition_name, diagnosis_date, notes) VALUES (?,?,?,?)',
                           (pid, cond[0], cond[1], cond[2]))

    today = date.today()
    appointments = [
        (1, 2, today.isoformat(), '09:00', 'General checkup', 'scheduled', 'phone'),
        (2, 3, today.isoformat(), '10:00', 'Blood pressure review', 'confirmed', 'online'),
        (3, 2, today.isoformat(), '11:30', 'Follow-up', 'scheduled', 'phone'),
        (4, 4, (today + timedelta(days=1)).isoformat(), '14:00', 'Annual physical', 'scheduled', 'phone'),
        (5, 5, (today + timedelta(days=2)).isoformat(), '08:30', 'Diabetes management', 'scheduled', 'online'),
        (6, 2, (today + timedelta(days=1)).isoformat(), '15:00', 'Chest pain', 'scheduled', 'phone'),
        (7, 3, today.isoformat(), '12:00', 'Migraine consultation', 'scheduled', 'phone'),
        (8, 4, today.isoformat(), '16:00', 'General consultation', 'in_progress', 'phone'),
    ]

    for a in appointments:
        db.execute(
            'INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status, type, created_by) VALUES (?,?,?,?,?,?,?,1)',
            a)

    consultations = [
        (1, 2, 'general', 'Patient in good health. Blood pressure normal.'),
        (3, 2, 'internal_medicine', 'Asthma well controlled. Continue current medication.'),
        (8, 4, 'general', 'Mild fever and cough. Prescribed antibiotics.'),
    ]
    for c in consultations:
        db.execute('INSERT INTO consultations (patient_id, doctor_id, consultation_type, diagnosis, notes) VALUES (?,?,?,?,?)',
                   (c[0], c[1], c[2], c[2], c[3]))

    pharmacy_items = [
        ('Amoxicillin 500mg', 'Amoxicillin', 'Antibiotics', 500, 50.00, '2026-12-31', 'Mediplus Ltd', 50),
        ('Paracetamol 500mg', 'Paracetamol', 'Analgesics', 1000, 10.00, '2027-06-30', 'PharmaCo', 100),
        ('Ibuprofen 400mg', 'Ibuprofen', 'Analgesics', 300, 15.00, '2026-09-30', 'PharmaCo', 50),
        ('Metformin 850mg', 'Metformin', 'Diabetes', 400, 30.00, '2026-08-31', 'Mediplus Ltd', 30),
        ('Amlodipine 5mg', 'Amlodipine', 'Hypertension', 200, 25.00, '2026-11-30', 'HealthPharm', 25),
        ('Salbutamol Inhaler', 'Salbutamol', 'Respiratory', 50, 800.00, '2025-12-31', 'Mediplus Ltd', 10),
        ('Omeprazole 20mg', 'Omeprazole', 'GI', 250, 20.00, '2027-03-31', 'PharmaCo', 30),
        ('Cetirizine 10mg', 'Cetirizine', 'Antihistamines', 150, 8.00, '2027-01-31', 'HealthPharm', 40),
        ('Diclofenac Gel', 'Diclofenac', 'Topical', 80, 350.00, '2026-10-31', 'Mediplus Ltd', 15),
        ('Multivitamin Tablets', 'Multivitamin', 'Supplements', 600, 5.00, '2027-12-31', 'HealthPharm', 100),
    ]

    for item in pharmacy_items:
        db.execute(
            'INSERT INTO pharmacy_inventory (drug_name, generic_name, category, stock_quantity, unit_price, expiry_date, supplier, reorder_level) VALUES (?,?,?,?,?,?,?,?)',
            item)

    packages = [
        ('Annual Health Checkup', 'Comprehensive annual health screening', 5000.00),
        ('Maternity Package', 'Antenatal and postnatal care', 15000.00),
        ('Diabetes Care Plan', 'Monthly diabetes management', 3000.00),
        ('Executive Wellness', 'Executive health and wellness package', 25000.00),
    ]

    for pkg in packages:
        db.execute('INSERT INTO packages (package_name, description, total_amount) VALUES (?,?,?)', pkg)

    package_services = [
        (1, 'Full blood count', 'lab'), (1, 'Blood sugar test', 'lab'), (1, 'Urinalysis', 'lab'),
        (1, 'ECG', 'procedure'), (1, 'General consultation', 'consultation'),
        (2, 'Antenatal consultation', 'consultation'), (2, 'Ultrasound scan', 'lab'), (2, 'Blood tests', 'lab'),
        (3, 'HbA1c test', 'lab'), (3, 'Dietary consultation', 'consultation'), (3, 'Monthly checkup', 'consultation'),
        (4, 'Full blood count', 'lab'), (4, 'Lipid profile', 'lab'), (4, 'ECG', 'procedure'),
        (4, 'Stress test', 'procedure'), (4, 'Nutrition plan', 'consultation'),
    ]

    for ps in package_services:
        db.execute('INSERT INTO package_services (package_id, service_name, service_type) VALUES (?,?,?)', ps)

    db.commit()
    db.close()
    print('Database seeded successfully!')
    print('\nDefault logins:')
    print('  Admin:      admin / admin123')
    print('  Doctor:     dr.main / doctor123')
    print('  Nurse:      nurse.main / nurse123')
    print('  Lab:        lab.tech1 / lab123')
    print('  Front Desk: front.desk1 / front123')
    print('  File Mgr:   file.mgr1 / file123')


if __name__ == '__main__':
    seed()
