"""User-initiated clipboard copy, with an editable text selection fallback."""
import base64
from html import escape
import streamlit.components.v1 as components
from branding import font_css


def clipboard_html(matrix):
    tsv = matrix.to_csv(sep='\t',index=False,lineterminator='\n')
    # Inline styles survive rich-table paste better than external CSS classes.
    base_style = "font-family:Manrope,sans-serif;font-size:12px;padding:8px;border:1px solid #E3E6E7;"
    table = '<table style="border-collapse:collapse;color:#092433"><thead><tr>'
    for name in matrix.columns:
        table += '<th style="'+base_style+'background:#092433;color:white">'+escape(str(name))+'</th>'
    table += '</tr></thead><tbody>'
    for row in matrix.itertuples(index=False,name=None):
        table += '<tr>'
        for name,value in zip(matrix.columns,row):
            style = base_style + ('background:#FFF4F4;border-left:1px solid #EB4247;border-right:1px solid #EB4247;' if name == 'Selectel' else '')
            table += '<td style="'+style+'">'+escape(str(value))+'</td>'
        table += '</tr>'
    table += '</tbody></table>' 
    b64 = lambda s: base64.b64encode(s.encode('utf-8')).decode('ascii')
    return '''<!doctype html><html lang="ru"><meta charset="utf-8"><style>'''+font_css()+'''
body{margin:0;font:13px Manrope,sans-serif;color:#092433;background:white}
button{font:600 14px Manrope,sans-serif;border:0;border-radius:6px;background:#EB4247;color:white;padding:10px 16px;cursor:pointer}
button.secondary{background:#E3E6E7;color:#092433;margin-left:8px}#status{margin:8px 0;min-height:20px}
textarea{width:100%;height:62px;box-sizing:border-box;font:12px Manrope,sans-serif;border:1px solid #CDD2D5;border-radius:4px;padding:6px;white-space:pre;}
#rich{position:absolute;left:-10000px;top:0}table{border-collapse:collapse}td,th{padding:6px;border:1px solid #CDD2D5}
</style><button id="copy">Скопировать всю таблицу</button><button id="select" class="secondary">Выделить текст</button><div id="status" role="status">Вставьте в Excel, Google Sheets или документ через Ctrl+V (на Mac — ⌘V).</div><textarea id="plain" readonly aria-label="Таблица для копирования"></textarea><div id="rich"></div><script>
const decode=s=>new TextDecoder().decode(Uint8Array.from(atob(s),c=>c.charCodeAt(0)));
const tsv=decode("'''+b64(tsv)+'''");
const html=decode("'''+b64(table)+'''");
const plain=document.getElementById('plain'); plain.value=tsv;
const rich=document.getElementById('rich'); rich.innerHTML=html;
const status=document.getElementById('status');
function selectText(){plain.focus();plain.select();status.textContent='Текст выделен. Нажмите Ctrl+C (на Mac — ⌘C), затем вставьте в таблицу.';}
document.getElementById('select').addEventListener('click',selectText);
document.getElementById('copy').addEventListener('click',async()=>{
  let copied=false;
  const onCopy=event=>{event.clipboardData.setData('text/plain',tsv);event.clipboardData.setData('text/html',html);event.preventDefault();};
  document.addEventListener('copy',onCopy);
  const range=document.createRange();range.selectNodeContents(rich);
  const selection=window.getSelection();selection.removeAllRanges();selection.addRange(range);
  try{copied=document.execCommand('copy');}catch(error){}
  document.removeEventListener('copy',onCopy);selection.removeAllRanges();
  if(!copied && navigator.clipboard){
    try{
      if(window.ClipboardItem){await navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([tsv],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})]);}
      else{await navigator.clipboard.writeText(tsv);}
      copied=true;
    }catch(error){}
  }
  if(copied){status.textContent='Таблица скопирована. Вставьте её через Ctrl+V (⌘V).';}
  else{selectText();}
});
</script></html>'''


def render_clipboard(matrix):
    components.html(clipboard_html(matrix),height=175,scrolling=False)
