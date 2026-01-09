from flask import Flask, render_template, redirect, url_for

app = Flask(__name__)

# Route untuk halaman utama - redirect ke dashboard
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

# Route Dashboard4
@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

# Route Schedule
@app.route('/schedule')
def schedule():
    return render_template('schedule.html')

# Route Tambah Reservasi
@app.route('/reservation')
def reservation():
    return render_template('reservation.html')

# Route Kelola User (Admin)
@app.route('/user')
def user():
    return render_template('user.html')

# Route Tambah User (Admin)
@app.route('/add_user')
def add_user():
    return render_template('add_user.html')

# Route Login
@app.route('/login')
def login():
    return render_template('login.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)