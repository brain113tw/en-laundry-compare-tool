"""Regenerates the synthetic HEIC fixtures in tests/fixtures/ and the colours the tests expect from them.

Only needed when the fixtures themselves have to change: the committed files are what tests/check_heic.py reads.
Needs Python with Pillow and pillow-heif (which brings its own libheif and HEVC encoder).

Every picture is a 4 x 3 board of flat colour patches, never a customer photo. The expected colours written to
heic_expected.json are derived from the patch colours themselves (turned, mirrored and colour-converted as the file says),
not from another decoder; this script then checks that the reference decoder agrees with them.
"""
from pathlib import Path
from PIL import Image, ImageCms
import hashlib, io, json, struct, sys

import pillow_heif

pillow_heif.register_heif_opener()
out_dir = Path(__file__).resolve().parent / 'fixtures'
CELL = 32
BOARD = [[(200, 60, 60), (60, 170, 80), (50, 80, 200), (128, 128, 128)],
         [(255, 0, 0), (0, 255, 0), (240, 200, 40), (20, 20, 20)],
         [(235, 235, 235), (180, 90, 200), (30, 160, 170), (255, 128, 0)]]
ALPHA = [[255, 128, 255, 64], [255, 255, 0, 255], [128, 255, 255, 255]]
TURN = {1: None, 5: Image.Transpose.TRANSPOSE, 6: Image.Transpose.ROTATE_270}


def board(alpha=False):
    im = Image.new('RGBA' if alpha else 'RGB', (CELL * 4, CELL * 3))
    for r, row in enumerate(BOARD):
        for c, col in enumerate(row):
            im.paste(col + ((ALPHA[r][c],) if alpha else ()), (c * CELL, r * CELL, (c + 1) * CELL, (r + 1) * CELL))
    return im


# ---- Display P3 as an ICC profile, built from its published primaries (not copied from any vendor's file).
def mat_mul(a, b): return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def mat_vec(a, v): return [sum(a[i][k] * v[k] for k in range(3)) for i in range(3)]


def mat_inv(m):
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def xyz_of(x, y): return [x / y, 1.0, (1 - x - y) / y]


def rgb_to_xyz(primaries, white):
    cols = [xyz_of(*p) for p in primaries]
    m = [[cols[j][i] for j in range(3)] for i in range(3)]
    s = mat_vec(mat_inv(m), white)
    return [[m[i][j] * s[j] for j in range(3)] for i in range(3)]


D65, D50 = xyz_of(.3127, .3290), [.9642, 1.0, .8249]
BRADFORD = [[.8951, .2664, -.1614], [-.7502, 1.7135, .0367], [.0389, -.0685, 1.0296]]
src_cone, dst_cone = mat_vec(BRADFORD, D65), mat_vec(BRADFORD, D50)
ADAPT = mat_mul(mat_inv(BRADFORD), mat_mul([[dst_cone[0] / src_cone[0], 0, 0], [0, dst_cone[1] / src_cone[1], 0], [0, 0, dst_cone[2] / src_cone[2]]], BRADFORD))
P3 = rgb_to_xyz([(.680, .320), (.265, .690), (.150, .060)], D65)
SRGB = rgb_to_xyz([(.640, .330), (.300, .600), (.150, .060)], D65)


def s15(v): return struct.pack('>i', int(round(v * 65536)))


def display_p3_icc():
    colorants = mat_mul(ADAPT, P3)
    xyz = lambda v: b'XYZ \0\0\0\0' + b''.join(s15(c) for c in v)
    text = lambda t: b'mluc\0\0\0\0' + struct.pack('>II', 1, 12) + b'enUS' + struct.pack('>II', len(t) * 2, 28) + t.encode('utf-16-be')
    curve = b'para\0\0\0\0' + struct.pack('>HH', 3, 0) + s15(2.4) + s15(1 / 1.055) + s15(.055 / 1.055) + s15(1 / 12.92) + s15(.04045)
    tags = [(b'desc', text('Display P3 (test fixture)')), (b'cprt', text('No copyright, test data')), (b'wtpt', xyz(D50)),
            (b'chad', b'sf32\0\0\0\0' + b''.join(s15(c) for row in ADAPT for c in row)),
            (b'rXYZ', xyz([colorants[i][0] for i in range(3)])), (b'gXYZ', xyz([colorants[i][1] for i in range(3)])), (b'bXYZ', xyz([colorants[i][2] for i in range(3)])),
            (b'rTRC', curve), (b'gTRC', curve), (b'bTRC', curve)]
    table, body, offset, seen = b'', b'', 128 + 4 + 12 * len(tags), {}
    for name, data in tags:
        if data not in seen:
            seen[data] = (offset + len(body), len(data))
            body += data + b'\0' * (-len(data) % 4)
        table += name + struct.pack('>II', *seen[data])
    size = 128 + 4 + len(table) + len(body)
    head = struct.pack('>I4s4s4s4s4s6H4s4sI4s4s8sI', size, b'\0' * 4, b'\x04\x30\0\0', b'mntr', b'RGB ', b'XYZ ', 2024, 1, 1, 0, 0, 0, b'acsp', b'\0' * 4, 0, b'\0' * 4, b'\0' * 4, b'\0' * 8, 0)
    head += b''.join(s15(c) for c in D50) + b'\0' * 48
    assert len(head) == 128, len(head)
    return head + struct.pack('>I', len(tags)) + table + body


P3_ICC = display_p3_icc()


def p3_to_srgb(rgb):
    """Reference conversion with LittleCMS, cross-checked against plain arithmetic."""
    transform = ImageCms.buildTransform(ImageCms.ImageCmsProfile(io.BytesIO(P3_ICC)), ImageCms.createProfile('sRGB'), 'RGB', 'RGB', renderingIntent=ImageCms.Intent.RELATIVE_COLORIMETRIC)
    lcms = ImageCms.applyTransform(Image.new('RGB', (1, 1), rgb), transform).getpixel((0, 0))
    lin = lambda c: c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4
    enc = lambda c: 12.92 * c if c <= .0031308 else 1.055 * c ** (1 / 2.4) - .055
    direct = mat_vec(mat_mul(mat_inv(SRGB), P3), [lin(v / 255) for v in rgb])
    plain = tuple(round(255 * enc(min(1, max(0, v)))) for v in direct)
    assert max(abs(a - b) for a, b in zip(lcms, plain)) <= 1, ('colour engines disagree', rgb, lcms, plain)
    return plain


# ---- A second colour box on the primary item, so one file can carry both an nclx description and an ICC profile.
def boxes(b, start, end):
    o = start
    while o + 8 <= end:
        size, kind = struct.unpack('>I4s', b[o:o + 8])
        assert size >= 8 and o + size <= end, (kind, size)
        yield kind, o, o + size
        o += size


def add_icc_box(data, icc):
    find = lambda kind, start, end: next((s, e) for k, s, e in boxes(data, start, end) if k == kind)
    meta = find(b'meta', 0, len(data)); inner = (meta[0] + 12, meta[1])
    iprp = find(b'iprp', *inner); ipco = find(b'ipco', iprp[0] + 8, iprp[1]); ipma = find(b'ipma', iprp[0] + 8, iprp[1])
    iloc = find(b'iloc', *inner); pitm = find(b'pitm', *inner)
    primary = struct.unpack('>H', data[pitm[0] + 12:pitm[0] + 14])[0]
    index = len(list(boxes(data, ipco[0] + 8, ipco[1]))) + 1
    new_box = struct.pack('>I4s4s', 12 + len(icc), b'colr', b'prof') + icc
    # ipma (version 0, one-byte associations): find the primary item's entry and append the new property to it.
    assert data[ipma[0] + 8] == 0 and data[ipma[0] + 11] & 1 == 0 and index < 128
    o, at = ipma[0] + 16, None
    for _ in range(struct.unpack('>I', data[ipma[0] + 12:ipma[0] + 16])[0]):
        item, count = struct.unpack('>HB', data[o:o + 3])
        if item == primary: at = (o + 2, o + 3 + count)
        o += 3 + count
    assert at and ipco[1] <= ipma[0] < iprp[1]
    grow = len(new_box) + 1
    out = bytearray(data[:ipco[1]] + new_box + data[ipco[1]:at[1]] + bytes([index]) + data[at[1]:])
    out[at[0] + len(new_box)] += 1
    for start, extra in ((meta[0], grow), (iprp[0], grow), (ipco[0], len(new_box)), (ipma[0] + len(new_box), 1)):
        struct.pack_into('>I', out, start, struct.unpack('>I', out[start:start + 4])[0] + extra)
    # iloc: everything stored after the meta box has moved.
    assert iloc[1] <= iprp[0]
    version, sizes, sizes2 = out[iloc[0] + 8], out[iloc[0] + 12], out[iloc[0] + 13]
    offset_size, length_size, base_size, index_size = sizes >> 4, sizes & 15, sizes2 >> 4, sizes2 & 15 if version else 0
    assert version in (0, 1) and offset_size == 4 and base_size in (0, 4)
    o = iloc[0] + 16
    for _ in range(struct.unpack('>H', out[iloc[0] + 14:iloc[0] + 16])[0]):
        o += 2
        method = 0
        if version == 1: method = struct.unpack('>H', out[o:o + 2])[0] & 15; o += 2
        o += 2
        base_at = o; o += base_size
        extents = struct.unpack('>H', out[o:o + 2])[0]; o += 2
        for n in range(extents):
            o += index_size
            if method == 0 and (base_size == 0 or (n == 0 and struct.unpack('>I', out[base_at:base_at + 4])[0] == 0)):
                struct.pack_into('>I', out, o, struct.unpack('>I', out[o:o + 4])[0] + grow)
            o += offset_size + length_size
        if method == 0 and base_size and struct.unpack('>I', out[base_at:base_at + 4])[0]:
            struct.pack_into('>I', out, base_at, struct.unpack('>I', out[base_at:base_at + 4])[0] + grow)
    return bytes(out)


def exif_orientation(n):
    ex = Image.Exif(); ex[0x0112] = n
    return ex.tobytes()


FIXTURES = [
    # name, orientation, colour the file declares, what the decoder is expected to report, extra save options
    ('heic_patches.heic', 1, 'srgb', '', {}),
    ('heic_rotated.heic', 6, 'srgb', '', {}),
    ('heic_mirrored.heic', 5, 'srgb', '', {}),
    ('heic_grid.heic', 1, 'srgb', '', {'tile_size': 64}),
    ('heic_p3_icc.heic', 1, 'p3', 'p3', {'icc_profile': P3_ICC}),
    ('heic_p3_nclx.heic', 1, 'p3', 'p3', {'color_primaries': 12, 'transfer_characteristics': 13, 'matrix_coefficients': 6, 'full_range_flag': 1}),
    ('heic_p3_both.heic', 1, 'p3', 'p3', {'add_icc': True}),
    ('heic_bt2020.heic', 1, 'srgb', 'other', {'color_primaries': 9, 'transfer_characteristics': 13, 'matrix_coefficients': 6, 'full_range_flag': 1}),
    ('heic_phone_like.heic', 6, 'p3', 'p3', {'tile_size': 64, 'icc_profile': P3_ICC, 'chroma': 420}),
    ('heic_alpha.heic', 1, 'srgb', '', {'alpha': True}),
]


def build():
    expected = {'note': 'Written by tests/make_heic_fixtures.py. Samples are [x, y, [r, g, b, a]] at patch centres, in the picture as it should be displayed.', 'cell': CELL, 'files': {}}
    worst = 0
    for name, orientation, declared, reports, options in FIXTURES:
        options = dict(options)
        alpha, add_icc = options.pop('alpha', False), options.pop('add_icc', False)
        source = board(alpha)
        buf = io.BytesIO()
        kw = {'quality': 95, 'chroma': 444, **options}
        if orientation != 1: kw['exif'] = exif_orientation(orientation)
        source.save(buf, format='HEIF', **kw)
        data = buf.getvalue()
        # The file says BT.709 in its nclx box and Display P3 in its ICC profile: the profile is the one that counts.
        if add_icc: data = add_icc_box(data, P3_ICC)
        shown = source.transpose(TURN[orientation]) if TURN[orientation] else source
        samples = []
        for y in range(CELL // 2, shown.height, CELL):
            for x in range(CELL // 2, shown.width, CELL):
                px = shown.getpixel((x, y))
                rgb = p3_to_srgb(px[:3]) if declared == 'p3' else px[:3]
                samples.append([x, y, [*rgb, px[3] if alpha else 255]])
        # The reference decoder must agree with the patch colours before the fixture is accepted.
        ref = Image.open(io.BytesIO(data)); ref.load()
        assert ref.size == shown.size, (name, ref.size, shown.size)
        assert bool(ref.info.get('icc_profile')) == ('icc_profile' in options or add_icc), name
        for x, y, want in samples:
            got = ref.convert('RGBA').getpixel((x, y))
            stored = shown.getpixel((x, y))
            err = max(abs(a - b) for a, b in zip(got[:3], stored[:3])) if got[3] else 0
            worst = max(worst, err, abs(got[3] - (stored[3] if alpha else 255)))
        (out_dir / name).write_bytes(data)
        expected['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data), 'width': shown.width, 'height': shown.height,
                                   'opaque': not alpha, 'reports': reports, 'samples': samples}
        print('%-22s %5d bytes  %3d x %-3d  %s' % (name, len(data), shown.width, shown.height, reports or 'sRGB'))
    assert worst <= 3, ('reference decoder is too far from the patch colours', worst)
    expected['reference'] = 'pillow-heif %s (libheif %s) decodes every fixture within %d of the patch colours' % (pillow_heif.__version__, pillow_heif.libheif_version(), worst)
    (out_dir / 'heic_expected.json').write_text(json.dumps(expected, indent=1) + '\n', encoding='utf-8')
    print(expected['reference'])


if __name__ == '__main__':
    build()
    sys.exit(0)
