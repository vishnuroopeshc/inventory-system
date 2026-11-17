# Inventory Management & Demand Forecasting System

A Flask web app to track stock across cities and forecast product demand.

## Features
- User login / registration (hashed passwords)
- Dashboard with inventory and forecast summary
- City-wise stock vs. customer orders, with shortage/adequate status
- Add / remove stock per location
- Demand forecasting per product type using Prophet (90 days ahead)

## Tech Stack
Python, Flask, MySQL, Pandas, Prophet, Chart.js, Tailwind CSS

## Setup
```bash
git clone https://github.com/vishnuroopeshc/inventory-system.git
cd inventory-system
pip install -r requirements.txt
cp .env.example .env
python app.py
```
Fill in your values in `.env`. You need a MySQL database with these tables: `users`, `product_info`, `supply_chain_data`.

## Screenshots
![Login](screenshots/login.jpeg)
![Dashboard](screenshots/dashboard.jpeg)
![Inventory](screenshots/inventory.jpeg)
![Update Stock](screenshots/update-stock.jpeg)
![Forecast](screenshots/forecast.jpeg)