import os
from dotenv import load_dotenv
from flask import Flask, request, render_template, session, redirect, url_for, flash, jsonify
import mysql.connector
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from prophet import Prophet
from datetime import datetime, timedelta
import plotly.graph_objects as go
from sqlalchemy import create_engine
import json
from functools import wraps

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Configuration
app.config['DB_CONFIG'] = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

# Decorator for login required
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('home'))
        return f(*args, **kwargs)
    return decorated_function

# MySQL connection
def get_db_connection():
    return mysql.connector.connect(**app.config['DB_CONFIG'])

@app.route('/')
def home():
    return render_template('login.html', message='')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    action = request.form['action']  # 'login' or 'register'

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cursor.fetchone()

        if action == 'register':
            if user:
                msg = "❌ Username already exists. Please try a different one."
            else:
                hashed_password = generate_password_hash(password)
                cursor.execute("INSERT INTO users (username, password) VALUES (%s, %s)", 
                              (username, hashed_password))
                conn.commit()
                msg = f"✅ Account created for {username}!"
        else:  # action == 'login'
            if user:
                if check_password_hash(user['password'], password):
                    session['username'] = username
                    session['role'] = user.get('role', 'user')  # Store user role
                    return redirect(url_for('dashboard'))
                else:
                    msg = "❌ Incorrect password!"
            else:
                msg = "❌ Username does not exist. Please register first."

        return render_template('login.html', message=msg)
    finally:
        cursor.close()
        conn.close()

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get all unique locations
        cursor.execute("SELECT DISTINCT location FROM product_info")
        locations = [row[0] for row in cursor.fetchall()]
        
        # Get data for default location (first one)
        default_location = locations[0] if locations else 'Mumbai'
        
        cursor.execute("""
            SELECT 
                product_type, 
                SUM(Stock_levels) AS before_stock,
                SUM(Order_quantities) AS customer_order,
                SUM(Stock_levels - Order_quantities) AS net_difference,
                location 
            FROM 
                product_info 
            WHERE 
                location = %s
            GROUP BY 
                product_type, location
        """, (default_location,))
        
        data = cursor.fetchall()
        
        return render_template('dashboard.html',
                            username=session['username'],
                            chart_data={
                                'labels': [row[0] for row in data],
                                'before_stock': [row[1] for row in data],
                                'customer_order': [row[2] for row in data],
                                'net_difference': [row[3] for row in data],
                                'locations': locations,
                                'current_location': default_location
                            })
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('home'))
    finally:
        cursor.close()
        conn.close()

@app.route('/get_location_data/<location>')
@login_required
def get_location_data(location):
    adjustment = request.args.get('adjustment', default=0, type=int)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Special query for Mumbai with adjusted stock
        if location == 'Mumbai':
            cursor.execute("""
                SELECT 
                    product_type, 
                    SUM(Stock_levels + 100) AS adjusted_stock,
                    SUM(Order_quantities) AS customer_order,
                    SUM(Order_quantities - Stock_levels) AS current_stock,
                    location 
                FROM 
                    product_info 
                WHERE 
                    location = 'Mumbai'
                GROUP BY 
                    product_type, location
            """)
        else:
            cursor.execute("""
                SELECT 
                    product_type, 
                    SUM(Stock_levels) AS before_stock,
                    SUM(Order_quantities) AS customer_order,
                    SUM(Stock_levels - Order_quantities) AS net_difference,
                    location 
                FROM 
                    product_info 
                WHERE 
                    location = %s
                GROUP BY 
                    product_type, location
            """, (location,))
        
        data = cursor.fetchall()
        
        return jsonify({
            'labels': [row[0] for row in data],
            'before_stock': [row[1] for row in data],
            'customer_order': [row[2] for row in data],
            'net_difference': [row[3] for row in data],
            'current_location': location
        })
    except mysql.connector.Error as err:
        return jsonify({'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/inventory_1')
@login_required
def inventory_popup():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                product_type, 
                SUM(Stock_levels) AS before_stock,
                SUM(Order_quantities) AS customer_order,
                SUM(Stock_levels - Order_quantities) AS net_difference,
                location 
            FROM 
                product_info 
            GROUP BY 
                product_type, location
            ORDER BY 
                location, product_type
        """)
        
        inventory_data = cursor.fetchall()
        
        cursor.execute("SELECT DISTINCT location FROM product_info")
        locations = [row[0] for row in cursor.fetchall()]
        
        return render_template('inventory1.html',
                            username=session['username'],
                            inventory_data=inventory_data,
                            locations=locations)
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()

@app.route('/inventory')
@login_required
def inventory():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        cursor.execute("SELECT * FROM products")
        products = cursor.fetchall()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total_items,
                SUM(CASE WHEN stock_level <= 5 THEN 1 ELSE 0 END) as low_stock,
                SUM(CASE WHEN stock_level = 0 THEN 1 ELSE 0 END) as out_of_stock
            FROM products
        ''')
        inventory_stats = cursor.fetchone()
        
        return render_template('inventory.html',
                             username=session['username'],
                             products=products,
                             inventory_stats=inventory_stats)
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()

@app.route('/add-product', methods=['POST'])
@login_required
def add_product():
    if session.get('role') != 'admin':
        flash("You don't have permission to perform this action", "error")
        return redirect(url_for('inventory'))
    
    product_id = request.form['product_id']
    product_name = request.form['product_name']
    category = request.form['category']
    price = request.form['price']
    stock_level = request.form['stock_level']
    supplier_id = request.form['supplier_id']
    supplier_name = request.form['supplier_name']
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO products (product_id, product_name, category, price, stock_level, supplier_id, supplier_name)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (product_id, product_name, category, price, stock_level, supplier_id, supplier_name))
        conn.commit()
        flash('Product added successfully!', 'success')
    except mysql.connector.IntegrityError:
        flash('Product ID already exists!', 'error')
    except mysql.connector.Error as err:
        flash(f'Database error: {err}', 'error')
    finally:
        cursor.close()
        conn.close()
    
    return redirect(url_for('inventory'))

@app.route('/update_stock_mysql', methods=['POST'])
@login_required
def update_stock_mysql():
    data = request.get_json()
    location = data.get('location')
    product_type = data.get('product_type')
    stock_change = data.get('stock_change')
    operation = data.get('operation', 'add')  # 'add' or 'subtract'
    
    if not all([location, product_type, stock_change]):
        return jsonify({'error': 'Missing required fields'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # First check current stock level if we're subtracting
        if operation == 'subtract':
            cursor.execute(
                "SELECT Stock_levels FROM product_info WHERE location = %s AND product_type = %s",
                (location, product_type)
            )
            result = cursor.fetchone()
            if not result:
                return jsonify({'error': 'Product not found'}), 404
                
            current_stock = result[0]
            if current_stock < stock_change:
                return jsonify({
                    'error': f'Insufficient stock. Current: {current_stock}, Attempted to subtract: {stock_change}'
                }), 400

        # Execute the SQL update with parameters
        if operation == 'subtract':
            query = """
                UPDATE product_info 
                SET Stock_levels = Stock_levels - %s 
                WHERE location = %s AND product_type = %s
            """
        else:
            query = """
                UPDATE product_info 
                SET Stock_levels = Stock_levels + %s 
                WHERE location = %s AND product_type = %s
            """
        
        cursor.execute(query, (stock_change, location, product_type))
        rows_affected = cursor.rowcount
        
        if rows_affected == 0:
            return jsonify({'error': 'No rows updated - product/location not found'}), 404
            
        conn.commit()
        
        return jsonify({
            'success': True,
            'location': location,
            'product_type': product_type,
            'stock_change': stock_change,
            'operation': operation,
            'rows_affected': rows_affected,
            'message': f'Successfully updated stock for {product_type} in {location}'
        })
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'error': str(err)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/hello.html')
@login_required
def update_stock_page():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get all unique locations
        cursor.execute("SELECT DISTINCT location FROM product_info")
        locations = [row[0] for row in cursor.fetchall()]
        
        # Get default location (first one)
        current_location = locations[0] if locations else 'Mumbai'
        
        # Get product types for default location
        cursor.execute("""
            SELECT DISTINCT product_type 
            FROM product_info 
            WHERE location = %s
            ORDER BY product_type
        """, (current_location,))
        product_types = [row[0] for row in cursor.fetchall()]
        
        # Get current stock data for chart
        if current_location == 'Mumbai':
            cursor.execute("""
                SELECT product_type, SUM(Stock_levels + 100) AS total_stock
                FROM product_info 
                WHERE location = 'Mumbai'
                GROUP BY product_type
            """)
        else:
            cursor.execute("""
                SELECT product_type, SUM(Stock_levels) AS total_stock
                FROM product_info 
                WHERE location = %s
                GROUP BY product_type
            """, (current_location,))
        
        stock_data = cursor.fetchall()
        
        chart_data = {
            'labels': [row[0] for row in stock_data],
            'values': [row[1] for row in stock_data]
        }
        
        return render_template('hello.html',
                            username=session['username'],
                            locations=locations,
                            current_location=current_location,
                            product_types=product_types,
                            chart_data=chart_data)
    except mysql.connector.Error as err:
        flash(f"Database error: {err}", "error")
        return redirect(url_for('dashboard'))
    finally:
        cursor.close()
        conn.close()

@app.route('/get_products_for_location/<location>')
@login_required
def get_products_for_location(location):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT DISTINCT product_type 
            FROM product_info 
            WHERE location = %s
            ORDER BY product_type
        """, (location,))
        product_types = [row[0] for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'product_types': product_types
        })
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'error': str(err)})
    finally:
        cursor.close()
        conn.close()

@app.route('/update_stock', methods=['POST'])
@login_required
def update_stock():
    product_type = request.form['product_type']
    location = request.form['location']
    adjustment = int(request.form['adjustment'])
    action = request.form['action']  # 'add' or 'remove'
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get current stock
        cursor.execute("""
            SELECT Stock_levels FROM product_info 
            WHERE product_type = %s AND location = %s
        """, (product_type, location))
        result = cursor.fetchone()
        
        if result:
            current_stock = result[0]
            new_stock = current_stock + adjustment if action == 'add' else current_stock - adjustment
            new_stock = max(0, new_stock)  # Prevent negative stock
            
            # Update stock
            cursor.execute("""
                UPDATE product_info 
                SET Stock_levels = %s 
                WHERE product_type = %s AND location = %s
            """, (new_stock, product_type, location))
            conn.commit()
            
            # Get updated data for chart
            if location == 'Mumbai':
                cursor.execute("""
                    SELECT product_type, SUM(Stock_levels + 100) AS total_stock
                    FROM product_info 
                    WHERE location = 'Mumbai'
                    GROUP BY product_type
                """)
            else:
                cursor.execute("""
                    SELECT product_type, SUM(Stock_levels) AS total_stock
                    FROM product_info 
                    WHERE location = %s
                    GROUP BY product_type
                """, (location,))
            
            updated_data = cursor.fetchall()
            
            return jsonify({
                'success': True,
                'new_stock': new_stock,
                'chart_data': {
                    'labels': [row[0] for row in updated_data],
                    'values': [row[1] for row in updated_data]
                }
            })
        else:
            return jsonify({'success': False, 'error': 'Product not found'})
    except mysql.connector.Error as err:
        return jsonify({'success': False, 'error': str(err)})
    finally:
        cursor.close()
        conn.close()

@app.route('/demand_forecast1')
@login_required
def demand_forcasting():
    forecast_service = ForecastService()
    products = forecast_service.get_product_list()
    
    return render_template(
        'demand_forecast.html',
        username=session['username'],
        products=products
    )

@app.route('/get_forecast_data')
@login_required
def get_forecast_data():
    product_type = request.args.get('product_type')
    if not product_type:
        return jsonify({'error': 'Product type required'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get historical data - ensure no negative values
        cursor.execute("""
            SELECT 
                Date as ds, 
                GREATEST(Number_of_products_sold, 0) as y 
            FROM supply_chain_data 
            WHERE product_type = %s AND Date IS NOT NULL
            ORDER BY Date
        """, (product_type,))
        history = cursor.fetchall()
        
        # Convert to DataFrame and clean data
        df = pd.DataFrame(history)
        df['ds'] = pd.to_datetime(df['ds'],format='%d-%m-%Y', dayfirst=True)
        df = df.drop_duplicates(subset=['ds'])  # Remove duplicate dates
        df = df.sort_values('ds')  # Ensure chronological order
        
        if len(df) < 2:
            return jsonify({'error': 'Not enough data points for forecasting'}), 400
        
        # Generate forecast
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model.fit(df)
        
        future = model.make_future_dataframe(periods=90)
        forecast = model.predict(future)
        
        # Prepare clean response data
        response = {
            'product': product_type,
            'actual': [{
                'date': row['ds'].strftime('%Y-%m-%d'),
                'demand': int(row['y'])
            } for _, row in df.iterrows()],
            'forecast': [{
                'date': row['ds'].strftime('%Y-%m-%d'),
                'forecast': float(row['yhat']),
                'lower': float(row['yhat_lower']),
                'upper': float(row['yhat_upper'])
            } for _, row in forecast.iterrows()]
        }
        
        return jsonify(response)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        cursor.close()
        conn.close()

@app.route('/pending_orders1')
@login_required
def pending_orders():
    return render_template('pending_orders.html', username=session['username'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

class ForecastService:
    def __init__(self):
        self.db_config = app.config['DB_CONFIG']
    
    def get_product_list(self):
        """Get list of all product types"""
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT DISTINCT product_type FROM supply_chain_data")
            products = [row[0] for row in cursor.fetchall()]
            return products
        finally:
            cursor.close()
            conn.close()
    
    def get_product_data(self, product_type):
        """Get historical data for a specific product"""
        engine = create_engine(
            f"mysql+mysqlconnector://{self.db_config['user']}:{self.db_config['password']}@"
            f"{self.db_config['host']}/{self.db_config['database']}"
        )
        
        try:
            query = f"""
            SELECT Date, Number_of_products_sold as demand 
            FROM supply_chain_data 
            WHERE product_type = '{product_type}'
            ORDER BY Date
            """
            
            df = pd.read_sql(query, engine)
            
            # Preprocess data
            df['Date'] = pd.to_datetime(df['Date'])
            df = df.rename(columns={'Date': 'ds', 'demand': 'y'})
            df = df.dropna()
            
            return df
        finally:
            engine.dispose()
    
    def generate_forecast(self, product_type, periods=90):
        """Generate forecast for a product"""
        df = self.get_product_data(product_type)
        
        if len(df) < 2:
            return None  # Not enough data
        
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model.fit(df)
        
        future = model.make_future_dataframe(periods=periods)
        forecast = model.predict(future)
        
        return forecast
    
    def get_product_data_for_chart(self, product_type):
        """Get data formatted for Chart.js"""
        df = self.get_product_data(product_type)
        forecast = self.generate_forecast(product_type)
        
        if forecast is None:
            return None
            
        # Format historical data
        actual_data = [{
            'date': row['ds'].strftime('%Y-%m-%d'),
            'demand': row['y']
        } for _, row in df.iterrows()]
        
        # Format forecast data
        forecast_data = [{
            'date': row['ds'].strftime('%Y-%m-%d'),
            'forecast': row['yhat'],
            'lower': row['yhat_lower'],
            'upper': row['yhat_upper']
        } for _, row in forecast.iterrows()]
        
        return {
            'actual': actual_data,
            'forecast': forecast_data
        }
    
    def create_plotly_figure(self, product_type):
        """Create interactive Plotly figure for a product"""
        df = self.get_product_data(product_type)
        forecast = self.generate_forecast(product_type)
        
        if forecast is None:
            return None
            
        fig = go.Figure()
        
        # Add actual data
        fig.add_trace(go.Scatter(
            x=df['ds'],
            y=df['y'],
            name='Actual Demand',
            mode='markers',
            marker=dict(color='red', size=6)
        ))
        
        # Add forecast
        fig.add_trace(go.Scatter(
            x=forecast['ds'],
            y=forecast['yhat'],
            name='Forecast',
            line=dict(color='blue', width=2)
        ))
        
        # Add confidence interval
        fig.add_trace(go.Scatter(
            x=forecast['ds'],
            y=forecast['yhat_upper'],
            fill=None,
            mode='lines',
            line=dict(width=0),
            showlegend=False
        ))
        
        fig.add_trace(go.Scatter(
            x=forecast['ds'],
            y=forecast['yhat_lower'],
            fill='tonexty',
            mode='lines',
            line=dict(width=0),
            name='Confidence Interval'
        ))
        
        fig.update_layout(
            title=f'Demand Forecast for {product_type}',
            xaxis_title='Date',
            yaxis_title='Demand',
            hovermode='x unified',
            template='plotly_white'
        )
        
        return fig.to_json()

if __name__ == '__main__':
    app.run(debug=True)