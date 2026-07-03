from io import BytesIO


def svg_qr(payload):
    """Return an SVG QR code for a payload."""
    import qrcode
    import qrcode.image.svg

    image = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage)
    output = BytesIO()
    image.save(output)
    return output.getvalue().decode("utf-8")
