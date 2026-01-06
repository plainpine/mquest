from flask import render_template, request, Blueprint

bp = Blueprint('main', __name__)

@bp.route('/svg_preview', methods=['POST'])
def svg_preview():
    svg_data = request.form.get('svg_data', '')
    return render_template('svg_preview.html', svg_data=svg_data)