"""
crear_icono.py — Generador de Icono Oficial para App Gestión Personal.
Crea un icono profesional moderno en formato .ico con resoluciones múltiples (256, 128, 64, 32, 16).
Estilo: Minimalista, esmeralda premium (#059669 / #10b981) con detalles en oro/blanco.
"""
import os
from PIL import Image, ImageDraw, ImageFont

def crear_icono_financiero(output_path="icono.ico"):
    size = 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Fondo redondeado suave / cápsula cuadrada con degradado simulado
    # Fondo base verde esmeralda profundo
    draw.rounded_rectangle((12, 12, 244, 244), radius=54, fill=(6, 78, 59, 255), outline=(16, 185, 129, 255), width=4)
    # Capa interior brillante
    draw.rounded_rectangle((20, 20, 236, 236), radius=48, fill=(5, 150, 105, 255))

    # 2. Barra de gráfica ascendente estilizada (Crecimiento financiero)
    # Barra 1
    draw.rounded_rectangle((55, 150, 85, 200), radius=6, fill=(16, 185, 129, 255))
    # Barra 2
    draw.rounded_rectangle((98, 115, 128, 200), radius=6, fill=(52, 211, 153, 255))
    # Barra 3
    draw.rounded_rectangle((141, 80, 171, 200), radius=6, fill=(110, 231, 183, 255))

    # 3. Flecha curva hacia arriba / Moneda con signo '$'
    # Círculo de moneda dorada en la esquina superior derecha
    coin_center = (185, 75)
    coin_r = 38
    draw.ellipse((coin_center[0] - coin_r, coin_center[1] - coin_r, coin_center[0] + coin_r, coin_center[1] + coin_r), fill=(245, 158, 11, 255), outline=(251, 191, 36, 255), width=3)

    # Texto o símbolo '$' en la moneda
    try:
        font = ImageFont.truetype("arialbd.ttf", 46)
    except Exception:
        font = ImageFont.load_default()

    try:
        bbox = draw.textbbox((0, 0), "$", font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
    except Exception:
        tw, th = (18, 30)

    draw.text((coin_center[0] - tw / 2, coin_center[1] - th / 2 - 4), "$", font=font, fill=(255, 255, 255, 255))

    # Guardar en archivo .ico con todos los tamaños estándar de Windows
    img.save(
        output_path,
        format='ICO',
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    )
    print(f"Icono generado exitosamente en: {output_path}")

if __name__ == "__main__":
    crear_icono_financiero("icono.ico")
