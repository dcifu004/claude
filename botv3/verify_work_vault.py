from pathlib import Path
import importlib.util
import os

spec = importlib.util.spec_from_file_location('botv3', '/opt/botv3/botv3.py')
bot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot)
bot.validate_startup()
assert bot.ALLOW_WORK_VAULT
for root in (bot.PERSONAL_VAULT, bot.WORK_VAULT):
    assert root.is_dir()
    assert os.statvfs(root).f_flag & os.ST_RDONLY, 'Vault mount is writable'
    print(root.name + ': readable, read-only mount', flush=True)
try:
    list(Path('/opt/nodo/datos/secretos').iterdir())
except OSError:
    print('Secrets inaccessible', flush=True)
else:
    raise RuntimeError('Secrets directory visible')
source = bot.WORK_VAULT / 'IA_INSTRUCCIONES.md'
if not source.is_file():
    raise RuntimeError('Expected work vault instructions missing')
prompt = ('Lee únicamente IA_INSTRUCCIONES.md en la raíz de vault_trabajo. '
          'Responde sólo si pudiste leerlo y cita vault_trabajo/IA_INSTRUCCIONES.md. '
          'No copies su contenido ni leas otros archivos ni sugieras comandos. '
          'Si la herramienta falla, incluye el mensaje técnico exacto del error en message, sin secretos.')
for agent in ('codex',):
    result = bot.invoke_agent(agent, prompt)
    if 'vault_trabajo/IA_INSTRUCCIONES.md' not in result['sources']:
        print('Diagnostic: ' + result['message'][:1800], flush=True)
    assert 'vault_trabajo/IA_INSTRUCCIONES.md' in result['sources'], agent + ': missing expected citation'
    print(agent + ': work vault read confirmed with citation', flush=True)
