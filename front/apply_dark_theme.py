"""Apply dark-theme class replacements to all render/util JS files and style.css."""
import re, os

BASE = os.path.dirname(os.path.abspath(__file__))

JS_FILES = [
    'src/render/header.js',
    'src/render/login.js',
    'src/render/fund.js',
    'src/render/project.js',
    'src/render/startup.js',
    'src/render/feedback.js',
    'src/render/calibrationQuiz.js',
    'src/utils/helpers.js',
    'src/notifications.js',
]

# Ordered: most specific first to avoid double-replacement
CLASS_REPLACEMENTS = [
    # ── Header bg with opacity ─────────────────────────────────────
    ('bg-white/80 backdrop-blur-md',        'bg-[#1A1A1A]/95 backdrop-blur-md'),
    ('bg-white/50',                          'bg-white/[.07]'),
    ('hover:bg-white/50',                    'hover:bg-white/[.10]'),
    # ── Login gradient ─────────────────────────────────────────────
    ('from-white via-surface to-primary-light',
     'from-surface via-[#1A1A1A] to-primary-light'),
    # ── Logo ring ─────────────────────────────────────────────────
    ('ring-black/[0.06]',                    'ring-white/[0.08]'),
    # ── CalibrationQuiz inner bg ───────────────────────────────────
    ('bg-white rounded-[14px]',              'bg-card rounded-[14px]'),
    # ── Generic white backgrounds ─────────────────────────────────
    ('bg-white ',                            'bg-card '),
    ("bg-white'",                            "bg-card'"),
    ('bg-white"',                            'bg-card"'),
    # ── Gray backgrounds ──────────────────────────────────────────
    ('bg-gray-50',                           'bg-[#222222]'),
    ('bg-gray-200',                          'bg-[#484848]'),
    ('bg-surface rounded-xl',               'bg-[#222222] rounded-xl'),
    # ── Hover backgrounds ─────────────────────────────────────────
    ('hover:bg-gray-50',                     'hover:bg-[#303030]'),
    ('hover:bg-white',                       'hover:bg-[#363636]'),
    ('hover:bg-surface',                     'hover:bg-[#222222]'),
    ('hover:bg-green-100',                   'hover:bg-green-900/30'),
    ('hover:bg-red-100',                     'hover:bg-red-900/30'),
    # ── Status / badge colored bg ─────────────────────────────────
    ('bg-blue-50',                           'bg-primary/[.10]'),
    ('bg-blue-100',                          'bg-primary/[.18]'),
    ('bg-green-100',                         'bg-green-900/[.30]'),
    ('bg-yellow-100',                        'bg-amber-900/[.30]'),
    ('bg-red-100',                           'bg-red-900/[.30]'),
    ('bg-red-50',                            'bg-red-900/[.20]'),
    ('bg-purple-100',                        'bg-purple-900/[.30]'),
    ('bg-green-50',                          'bg-green-900/[.20]'),
    # ── Borders ──────────────────────────────────────────────────
    ('border-gray-100',                      'border-card-border'),
    ('border-gray-200',                      'border-[#484848]'),
    ('border-gray-300',                      'border-[#555555]'),
    ('divide-gray-100',                      'divide-card-border'),
    ('border-green-200',                     'border-green-700/50'),
    ('border-red-200',                       'border-red-800/50'),
    ('border-yellow-200',                    'border-amber-700/50'),
    # ── Text: blue → primary ─────────────────────────────────────
    ('text-blue-600',                        'text-primary'),
    ('text-blue-700',                        'text-primary'),
    ('text-blue-900',                        'text-text-main'),
    # ── Text: colored status labels ───────────────────────────────
    ('text-green-600',                       'text-green-400'),
    ('text-green-700',                       'text-green-400'),
    ('text-yellow-600',                      'text-amber-400'),
    ('text-yellow-700',                      'text-amber-400'),
    ('text-red-500',                         'text-red-400'),
    ('text-red-600',                         'text-red-400'),
    ('text-red-700',                         'text-red-400'),
    ('text-purple-600',                      'text-purple-400'),
    ('text-purple-700',                      'text-purple-400'),
    ('text-gray-700',                        'text-text-main'),
    # ── Focus ring colors ────────────────────────────────────────
    ('focus:ring-2 focus:ring-primary',      'focus:ring-1 focus:ring-primary/60'),
    ('focus:border-transparent',             'focus:border-primary/50'),
    # ── Card shadow hover ─────────────────────────────────────────
    ('box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12)',
     'box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5)'),
]

def apply_js(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()
    for old, new in CLASS_REPLACEMENTS:
        src = src.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'  Patched: {os.path.relpath(path, BASE)}')

# ── helpers.js needs targeted status-color fixes ──────────────────────────────
def patch_helpers(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()

    # getStatusColor
    src = src.replace(
        "'Заявка принята': 'bg-blue-100 text-blue-700'",
        "'Заявка принята': 'bg-primary/[.18] text-primary'"
    )
    src = src.replace(
        "'На анализе': 'bg-yellow-100 text-yellow-700'",
        "'На анализе': 'bg-amber-900/[.35] text-amber-400'"
    )
    src = src.replace(
        "'Решение ИК': 'bg-purple-100 text-purple-700'",
        "'Решение ИК': 'bg-purple-900/[.35] text-purple-400'"
    )
    src = src.replace(
        "Результат: 'bg-green-100 text-green-700'",
        "Результат: 'bg-green-900/[.35] text-green-400'"
    )
    src = src.replace(
        "return colors[status] || 'bg-gray-100 text-gray-700'",
        "return colors[status] || 'bg-[#383838] text-text-secondary'"
    )

    # getRiskColor
    src = src.replace(
        "high: 'bg-red-100 text-red-700 border-red-200'",
        "high: 'bg-red-900/[.30] text-red-400 border-red-800/50'"
    )
    src = src.replace(
        "medium: 'bg-yellow-100 text-yellow-700 border-yellow-200'",
        "medium: 'bg-amber-900/[.30] text-amber-400 border-amber-700/50'"
    )
    src = src.replace(
        "low: 'bg-green-100 text-green-700 border-green-200'",
        "low: 'bg-green-900/[.30] text-green-400 border-green-700/50'"
    )
    src = src.replace(
        "return colors[severity] || 'bg-gray-100 text-gray-700'",
        "return colors[severity] || 'bg-[#383838] text-text-secondary'"
    )

    # getVerificationBadge
    src = src.replace(
        "'bg-green-100 text-green-700 text-xs rounded-full'",
        "'bg-green-900/[.35] text-green-400 text-xs rounded-full'"
    )
    src = src.replace(
        "'bg-blue-100 text-blue-700 text-xs rounded-full'",
        "'bg-primary/[.18] text-primary text-xs rounded-full'"
    )
    src = src.replace(
        "'bg-red-100 text-red-700 text-xs rounded-full'",
        "'bg-red-900/[.35] text-red-400 text-xs rounded-full'"
    )

    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'  Patched: {os.path.relpath(path, BASE)}')

# ── calibrationQuiz inline gradient ───────────────────────────────────────────
def patch_quiz(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()
    src = src.replace(
        'background: linear-gradient(135deg, #0071e3, #5856d6, #7c3aed)',
        'background: linear-gradient(135deg, #4D966F, #3D7D5C, #2D5E45)'
    )
    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'  Patched quiz gradient: {os.path.relpath(path, BASE)}')

# ── style.css ─────────────────────────────────────────────────────────────────
def patch_css(path):
    with open(path, encoding='utf-8') as f:
        src = f.read()

    # Tab active
    src = src.replace(
        'border-bottom: 2px solid #0071e3;\n  color: #0071e3;',
        'border-bottom: 2px solid #4D966F;\n  color: #4D966F;'
    )
    # Login btn hover
    src = src.replace(
        'background: #005bb5 !important;',
        'background: #3D7D5C !important;'
    )
    # Input focus
    src = src.replace(
        'border-color: #0071e3;\n  box-shadow: 0 0 0 3px rgba(0, 113, 227, 0.1);',
        'border-color: #4D966F;\n  box-shadow: 0 0 0 3px rgba(77, 150, 111, 0.18);'
    )
    # Scrollbar
    src = src.replace(
        'background: #f1f1f1;\n  border-radius: 4px;',
        'background: #2C2C2C;\n  border-radius: 4px;'
    )
    src = src.replace(
        'background: #c1c1c1;\n  border-radius: 4px;',
        'background: #4A4A4A;\n  border-radius: 4px;'
    )
    src = src.replace(
        '::-webkit-scrollbar-thumb:hover {\n  background: #a1a1a1;',
        '::-webkit-scrollbar-thumb:hover {\n  background: #5A5A5A;'
    )
    # card-hover dark shadow
    src = src.replace(
        'box-shadow: 0 12px 40px rgba(0, 0, 0, 0.12);',
        'box-shadow: 0 12px 40px rgba(0, 0, 0, 0.5);'
    )

    # Append dark input/textarea overrides
    dark_extras = """
/* ── Dark theme input/textarea ──────────────────────────────────── */
.input-field,
input[type="text"],
input[type="email"],
input[type="password"],
input[type="url"],
textarea {
  background-color: #2A2A2A;
  color: #F0F0F0;
  border-color: #484848;
}
.input-field::placeholder,
input::placeholder,
textarea::placeholder {
  color: #636366;
}
.input-field:focus,
input:focus,
textarea:focus {
  background-color: #333333;
}
"""
    src += dark_extras

    with open(path, 'w', encoding='utf-8') as f:
        f.write(src)
    print(f'  Patched CSS: {os.path.relpath(path, BASE)}')

# ── Run ───────────────────────────────────────────────────────────────────────
print('Applying dark theme to Pre-DD-v2...')
for rel in JS_FILES:
    full = os.path.join(BASE, rel)
    if rel == 'src/utils/helpers.js':
        patch_helpers(full)
    elif rel == 'src/render/calibrationQuiz.js':
        apply_js(full)
        patch_quiz(full)
    else:
        apply_js(full)

patch_css(os.path.join(BASE, 'src/style.css'))
print('Done!')
