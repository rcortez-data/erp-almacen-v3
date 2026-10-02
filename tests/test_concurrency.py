"""Pruebas basicas de concurrencia para folios SQLite."""

from concurrent.futures import ThreadPoolExecutor
import database


def test_folios_concurrentes_son_unicos_y_consecutivos(client):
    with ThreadPoolExecutor(max_workers=6) as pool:
        folios = list(pool.map(lambda _: database.next_folio('entrada'), range(12)))
    numeros = sorted(int(folio.split('-')[1]) for folio in folios)
    assert len(set(folios)) == 12
    assert numeros == list(range(1, 13))


def test_folios_requisicion_concurrentes_no_se_duplican(client):
    with ThreadPoolExecutor(max_workers=6) as pool:
        folios = list(pool.map(lambda _: database.next_folio_requisicion(), range(12)))
    assert sorted(folios) == list(range(1, 13))
