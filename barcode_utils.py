from html import escape


CODE128_PATTERNS = [
    "212222", "222122", "222221", "121223", "121322", "131222", "122213", "122312", "132212", "221213",
    "221312", "231212", "112232", "122132", "122231", "113222", "123122", "123221", "223211", "221132",
    "221231", "213212", "223112", "312131", "311222", "321122", "321221", "312212", "322112", "322211",
    "212123", "212321", "232121", "111323", "131123", "131321", "112313", "132113", "132311", "211313",
    "231113", "231311", "112133", "112331", "132131", "113123", "113321", "133121", "313121", "211331",
    "231131", "213113", "213311", "213131", "311123", "311321", "331121", "312113", "312311", "332111",
    "314111", "221411", "431111", "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114", "413111", "241112", "134111",
    "111242", "121142", "121241", "114212", "124112", "124211", "411212", "421112", "421211", "212141",
    "214121", "412121", "111143", "111341", "131141", "114113", "114311", "411113", "411311", "113141",
    "114131", "311141", "411131", "211412", "211214", "211232", "2331112",
]


def _encode_code128_b(texto):
    valores = [104]
    for caracter in str(texto):
        codigo = ord(caracter)
        if codigo < 32 or codigo > 126:
            raise ValueError("Code 128 B solo admite caracteres ASCII imprimibles.")
        valores.append(codigo - 32)
    checksum = valores[0] + sum(valor * indice for indice, valor in enumerate(valores[1:], start=1))
    valores.append(checksum % 103)
    valores.append(106)
    return valores


def code128_svg(texto, alto=58, modulo=2, margen=10, incluir_texto=True):
    """Devuelve un SVG Code 128-B para texto ASCII."""
    valores = _encode_code128_b(texto)
    texto_seguro = escape(str(texto), quote=True)
    patrones = [CODE128_PATTERNS[v] for v in valores]
    ancho_barras = sum(sum(int(n) for n in patron) for patron in patrones) * modulo
    ancho = ancho_barras + (margen * 2)
    alto_texto = 16 if incluir_texto else 0
    alto_total = alto + alto_texto + (margen * 2)
    x = margen
    rects = []
    for patron in patrones:
        barra = True
        for digito in patron:
            w = int(digito) * modulo
            if barra:
                rects.append(f'<rect x="{x}" y="{margen}" width="{w}" height="{alto}" fill="#111"/>')
            x += w
            barra = not barra
    texto_svg = ""
    if incluir_texto:
        y = margen + alto + 13
        texto_svg = (
            f'<text x="{ancho / 2}" y="{y}" text-anchor="middle" '
            f'font-family="Arial, sans-serif" font-size="12" fill="#111">{texto_seguro}</text>'
        )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto_total}" '
        f'viewBox="0 0 {ancho} {alto_total}" role="img" aria-label="{texto_seguro}">'
        f'<rect width="100%" height="100%" fill="#fff"/>'
        f'{"".join(rects)}{texto_svg}</svg>'
    )
