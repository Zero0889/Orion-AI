"""orion.adapters.messaging — Adapters para canales de mensajería externos.

Cada submódulo expone un cliente HTTP delgado + las tools decoradas con
``@tool`` que los autodiscover de tool_registry encuentran al arrancar.
Por ahora: Telegram. WhatsApp (via Twilio o Business API) seguiría el
mismo patrón en un archivo aparte.
"""
