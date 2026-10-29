"""Brand tokens supplied by the user; bundled Manrope under OFL-1.1."""
import base64
from functools import lru_cache
from pathlib import Path

SIGNAL_RED = '#EB4247'
DATA_BLUE = '#092433'
SERVER_GREY = '#E3E6E7'
WHITE = '#FFFFFF'
# Secondary neutral approximations; only the three tokens above were supplied as HEX.
TEXT_BLACK = '#1D2021'
COOL_GREY = '#CDD2D5'


@lru_cache(maxsize=1)
def font_css():
    root = Path(__file__).resolve().parent/'assets/fonts'
    ranges = {
        'cyrillic-ext': 'U+0460-052F,U+1C80-1C8A,U+20B4,U+2DE0-2DFF,U+A640-A69F,U+FE2E-FE2F',
        'cyrillic': 'U+0301,U+0400-045F,U+0490-0491,U+04B0-04B1,U+2116',
        'latin': 'U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD',
    }
    rules = []
    for subset, unicode_range in ranges.items():
        encoded = base64.b64encode((root/f'manrope-{subset}-wght-normal.woff2').read_bytes()).decode('ascii')
        rules.append("@font-face{font-family:Manrope;font-style:normal;font-display:swap;font-weight:200 800;src:url(data:font/woff2;base64,"+encoded+") format('woff2');unicode-range:"+unicode_range+";}")
    return '\n'.join(rules)


def app_css():
    return font_css()+'''
[data-testid="stApp"], [data-testid="stSidebar"], h1, h2, h3, h4, p, label, input, textarea, select, button {
    font-family:Manrope,sans-serif;
}
[data-testid="stSidebar"]{background:#092433;color:white}
[data-testid="stSidebar"] label,[data-testid="stSidebar"] p,[data-testid="stSidebar"] [data-testid="stCaptionContainer"]{color:white}
h1,h2,h3,h4{color:#092433;font-weight:400}
[data-testid="stMainBlockContainer"]{max-width:1600px}
'''
