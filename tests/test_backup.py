"""Pruebas de respaldo y restauracion simulada."""

import sqlite3
from scripts.backup_sqlite import create_backup
from scripts.verify_backup import verify
from scripts.restore_sqlite import restore


def test_backup_consistente_y_verificable(tmp_path):
    source = tmp_path / 'origen.db'
    conn = sqlite3.connect(source)
    conn.execute('CREATE TABLE prueba (id INTEGER PRIMARY KEY, valor TEXT)')
    conn.executemany('INSERT INTO prueba(valor) VALUES (?)', [('uno',), ('dos',)])
    conn.commit(); conn.close()
    backup = create_backup(source, tmp_path / 'backups', retention=2)
    assert backup.is_file()
    assert backup.with_suffix('.json').is_file()
    assert verify(backup) is True


def test_retencion_solo_conserva_cantidad_configurada(tmp_path):
    source = tmp_path / 'origen.db'
    conn = sqlite3.connect(source); conn.execute('CREATE TABLE prueba (id INTEGER)'); conn.close()
    output = tmp_path / 'backups'
    for _ in range(3):
        create_backup(source, output, retention=2)
    assert len(list(output.glob('almacen_auto_*.db'))) == 2


def test_restauracion_controlada_recupera_datos(tmp_path):
    source = tmp_path / 'origen.db'
    conn = sqlite3.connect(source); conn.execute('CREATE TABLE prueba(valor TEXT)'); conn.execute("INSERT INTO prueba VALUES ('correcto')"); conn.commit(); conn.close()
    backup = create_backup(source, tmp_path / 'backups')
    destination = tmp_path / 'destino.db'
    restore(backup, destination)
    conn = sqlite3.connect(destination); valor = conn.execute('SELECT valor FROM prueba').fetchone()[0]; conn.close()
    assert valor == 'correcto'
