"""
routes/views.py — Renderizado de vistas y páginas HTML.
"""
from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, request
from database import get_cached_config

views_bp = Blueprint('views', __name__)

@views_bp.route('/')
def index():
    return redirect(url_for('views.cuadre'))

@views_bp.route('/cuadre')
def cuadre():
    mes = request.args.get('mes')
    if not mes:
        mes = datetime.now().strftime('%Y-%m')
    config = get_cached_config()
    return render_template('cuadre.html', mes_actual=mes, config=config)

@views_bp.route('/proyeccion')
def proyeccion():
    config = get_cached_config()
    return render_template('proyeccion.html', config=config)
