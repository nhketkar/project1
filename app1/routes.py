from flask import request, render_template, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from .forms import LoginForm, RegisterForm
from .reco import get_recommendations,insert_recommendations
import os
import sqlite3
import datetime

def create_routes(app):

    def allowed_file(filename):
        """Check if the uploaded file has an allowed extension."""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    def get_db_connection():
        conn = sqlite3.connect('your_database.db')
        def dict_factory(cursor, row):
            d = {}
            for idx, col in enumerate(cursor.description):
                d[col[0]] = row[idx]
            return d
        conn.row_factory = dict_factory
        return conn

    @app.route('/', methods=['GET', 'POST'])
    def index():
     if request.method == 'POST':
         occasion = request.form.get('occasion')
         file = request.files.get('image')
         if file and allowed_file(file.filename):
             filename = secure_filename(file.filename)
             img_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
             file.save(img_path)

             try:
                user_id = session.get('user_id')
                user_gender = session.get('user_gender')  # Retrieve the user's gender
                if user_id and user_gender:  # Ensure there's a logged-in user and gender is known
                    recommended_image_paths, recommended_item_ids = get_recommendations(img_path, occasion, user_gender)
                    recommendations = list(zip(recommended_image_paths, recommended_item_ids))

                    # Insert recommendations into the database
                    insert_recommendations(user_id, recommended_item_ids)

                    return render_template('results.html', recommendations=recommendations)
                else:
                    flash("You need to log in and have gender information to get recommendations", "warning")
                    return redirect(url_for('login'))
             except Exception as e:
                 print(e)
                 return render_template('error.html', message="Error in processing the image.")
                
     return render_template('index.html')


    @app.route('/login', methods=['GET', 'POST'])
    def login():
     form = LoginForm()
     if form.validate_on_submit():
         conn = get_db_connection()
         cursor = conn.cursor()
         cursor.execute("SELECT * FROM users WHERE username = ?", (form.username.data,))
         user = cursor.fetchone()
         conn.close()

         if user and check_password_hash(user['password_hash'], form.password.data):
             flash('You have successfully logged in!', 'success')
             session['user_id'] = user['id']
             session['username'] = user['username']
             session['user_gender'] = user['gender']  # Store user's gender in the session
             return redirect(url_for('index'))
         else:
             flash('Invalid username or password', 'error')
             return redirect(url_for('login'))

     return render_template('login.html', form=form)


    @app.route('/register', methods=['GET', 'POST'])
    def register():
       form = RegisterForm()
       conn = None  # Initialize conn here
       try:
           if form.validate_on_submit():
               conn = get_db_connection()
               cursor = conn.cursor()
               # Check if username already exists
               cursor.execute('SELECT * FROM users WHERE username = ?', (form.username.data,))
               user = cursor.fetchone()
               if user:
                   flash('Username already exists. Please choose a different one.', 'danger')
                   return render_template('register.html', form=form)

               hashed_password = generate_password_hash(form.password.data)
               cursor.execute('''
                   INSERT INTO users (username, password_hash, age, gender, profession)
                   VALUES (?, ?, ?, ?, ?)
               ''', (form.username.data, hashed_password, form.age.data, form.gender.data, form.profession.data))
               conn.commit()
               flash('Registration successful!', 'success')
               return redirect(url_for('login'))
           else:
               if form.errors != {}:
                   for err_msg in form.errors.values():
                       flash(f'There was an error with creating a user: {err_msg}', 'danger')
       finally:
           if conn:
               conn.close()
       return render_template('register.html', form=form)



    @app.route('/logout')
    def logout():
        session.clear()  # Clear the session
        flash("You have been logged out.", "success")
        return redirect(url_for('index'))

    @app.route('/rate_item', methods=['POST'])
    def rate_item():
     data = request.json
     item_id = data['itemID']
     action = data['action']
     user_id = session.get('user_id')  # Assumes user ID is stored in the session

     conn = get_db_connection()
     cursor = conn.cursor()

     # Check if the item_id already exists in the item_ratings table
     cursor.execute('SELECT * FROM item_ratings WHERE item_id = ?', (item_id,))
     item = cursor.fetchone()

    # Handle likes and ratings for item_ratings table
     if action == 'like':
         if item:
            # Update existing record in item_ratings
            cursor.execute('''
                UPDATE item_ratings 
                SET num_likes = num_likes + 1 
                WHERE item_id = ?
            ''', (item_id,))
         else:
            # Insert new record into item_ratings
            cursor.execute('''
                INSERT INTO item_ratings (item_id, num_likes, average_rating, num_ratings)
                VALUES (?, 1, 0.0, 0)
            ''', (item_id,))

     elif action == 'rate':
         rating = int(data['rating']) if data['rating'].isdigit() else 0
         if item:
            # Update existing record in item_ratings
            cursor.execute('''
                UPDATE item_ratings 
                SET average_rating = ((average_rating * num_ratings) + ?) / (num_ratings + 1),
                    num_ratings = num_ratings + 1
                WHERE item_id = ?
            ''', (rating, item_id))
         else:
            # Insert new record into item_ratings
            cursor.execute('''
                INSERT INTO item_ratings (item_id, num_likes, average_rating, num_ratings)
                VALUES (?, 0, ?, 1)
            ''', (item_id, rating))

    # Check if there is already feedback for the given user-item pair
     cursor.execute('''
        SELECT * FROM feedback 
        WHERE user_id = ? AND recommendation_id = ?
     ''', (user_id, item_id))
     feedback = cursor.fetchone()

     if action == 'like':
         liked = True if action == 'like' else False
         if feedback:
             cursor.execute('''
                 UPDATE feedback 
                 SET liked = ?, 
                     feedback_date = CURRENT_TIMESTAMP
                 WHERE user_id = ? AND recommendation_id = ?
             ''', (liked, user_id, item_id))
         else:
             cursor.execute('''
                 INSERT INTO feedback 
                 (recommendation_id, user_id, rating, liked, feedback_date)
                 VALUES (?, ?, NULL, ?, CURRENT_TIMESTAMP)
             ''', (item_id, user_id, liked))

     elif action == 'rate':
         if feedback:
             cursor.execute('''
                 UPDATE feedback 
                 SET rating = ?, 
                     feedback_date = CURRENT_TIMESTAMP
                 WHERE user_id = ? AND recommendation_id = ?
             ''', (rating, user_id, item_id))
         else:
             cursor.execute('''
                 INSERT INTO feedback 
                (recommendation_id, user_id, rating, liked, feedback_date)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
             ''', (item_id, user_id, rating, feedback['liked'] if feedback else False))

     conn.commit()
     conn.close()
     return 'Success', 200



# Don't forget to call create_routes(app) in your main application file
