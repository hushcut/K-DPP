import 'dart:convert';
import 'dart:typed_data';

/// 업로드할 JPEG 에서 위치 정보를 지운 바이트를 돌려준다. 지울 것이 없으면 받은 바이트 그대로다.
///
/// 앨범 사진은 촬영 위치가 EXIF 의 GPS 칸에 들어 있어, 그대로 올리면 서버와 Google Vision 이
/// 위치를 받는다. 방향 값은 서버가 사진을 바로 세우는 데 쓰므로 남기고 위치만 지운다.
/// - EXIF: IFD0 의 GPSInfo 항목을 빼고 GPS IFD 와 그 값을 0 으로 덮는다. 조각 길이가 그대로라
///   다른 칸의 위치가 어긋나지 않는다. 안전하게 읽지 못하면 위치를 남기지 않도록 EXIF 조각을 뺀다.
/// - GPS 가 적힌 XMP 조각을 뺀다.
/// - 사진 끝(EOI) 뒤에 붙은 데이터(움직이는 사진의 영상·MPO 의 다른 사진)와 그 목록(MPF)을 뺀다.
///   분석에는 첫 사진만 쓰고, 붙은 영상에도 위치가 들어갈 수 있다.
///
/// JPEG 가 아니면(PNG·WEBP 등) 그대로 둔다.
Uint8List stripLocationMetadata(Uint8List bytes) {
  if (bytes.length < 4 || bytes[0] != 0xFF || bytes[1] != _soi) return bytes;

  final output = BytesBuilder(copy: false)
    ..add(Uint8List.sublistView(bytes, 0, 2));
  var changed = false;
  var position = 2;

  while (position + 2 <= bytes.length && bytes[position] == 0xFF) {
    final marker = bytes[position + 1];

    // 표지 앞 채움 바이트(0xFF)
    if (marker == 0xFF) {
      output.addByte(0xFF);
      position++;
      continue;
    }

    if (marker == _sos) {
      final imageEnd = _imageEnd(bytes, position);
      if (imageEnd != null && imageEnd < bytes.length) {
        output.add(Uint8List.sublistView(bytes, position, imageEnd));
        return output.takeBytes();
      }
      break;
    }

    if (marker == _eoi ||
        marker == 0x01 ||
        (marker >= 0xD0 && marker <= 0xD7)) {
      output.add(Uint8List.sublistView(bytes, position, position + 2));
      position += 2;
      continue;
    }

    if (position + 4 > bytes.length) break;
    final end =
        position + 2 + ((bytes[position + 2] << 8) | bytes[position + 3]);
    if (end < position + 4 || end > bytes.length) break;

    final segment = Uint8List.sublistView(bytes, position, end);
    final kept = _keptSegment(marker, segment);
    if (!identical(kept, segment)) changed = true;
    if (kept != null) output.add(kept);
    position = end;
  }

  if (!changed) return bytes;
  output.add(Uint8List.sublistView(bytes, position));
  return output.takeBytes();
}

const _soi = 0xD8;
const _eoi = 0xD9;
const _sos = 0xDA;
const _app1 = 0xE1;
const _app2 = 0xE2;
const _gpsInfoTag = 0x8825;

/// 조각 앞 4바이트(표지 2 + 길이 2) 뒤에 오는 이름표
const _exifName = 'Exif\x00\x00';
const _xmpNames = [
  'http://ns.adobe.com/xap/1.0/\x00',
  'http://ns.adobe.com/xmp/extension/\x00',
];
const _mpfName = 'MPF\x00';

/// TIFF 값 형식별 바이트 수(1 BYTE … 13 IFD)
const _tiffTypeSizes = {
  1: 1,
  2: 1,
  3: 2,
  4: 4,
  5: 8,
  6: 1,
  7: 1,
  8: 2,
  9: 4,
  10: 8,
  11: 4,
  12: 8,
  13: 4,
};

/// 남길 조각. 받은 조각 그대로면 바뀐 것이 없고, 사본이면 고친 것, null 이면 뺀다.
Uint8List? _keptSegment(int marker, Uint8List segment) {
  if (marker == _app1 && _hasName(segment, _exifName)) {
    return _exifWithoutGps(segment);
  }
  if (marker == _app1 && _xmpNames.any((name) => _hasName(segment, name))) {
    final text = latin1.decode(Uint8List.sublistView(segment, 4));
    return text.toLowerCase().contains('gps') ? null : segment;
  }
  if (marker == _app2 && _hasName(segment, _mpfName)) return null;
  return segment;
}

bool _hasName(Uint8List segment, String name) {
  if (segment.length < 4 + name.length) return false;
  for (var i = 0; i < name.length; i++) {
    if (segment[4 + i] != name.codeUnitAt(i)) return false;
  }
  return true;
}

/// 첫 사진의 끝(EOI 다음) 위치. 압축 데이터 안의 0xFF 뒤에는 0x00 이나 RST 가 오므로
/// 처음 만나는 0xFF 0xD9 가 끝이다. 못 찾으면 null.
int? _imageEnd(Uint8List bytes, int start) {
  for (var i = start + 2; i + 1 < bytes.length; i++) {
    if (bytes[i] == 0xFF && bytes[i + 1] == _eoi) return i + 2;
  }
  return null;
}

/// EXIF 조각에서 GPS 를 지운 사본. GPS 가 없으면 받은 조각, 안전하게 읽지 못하면 null.
Uint8List? _exifWithoutGps(Uint8List segment) {
  final tiffStart = 4 + _exifName.length;
  final copy = Uint8List.fromList(segment);
  final tiff = ByteData.sublistView(copy, tiffStart);

  try {
    final endian = switch ((tiff.getUint8(0), tiff.getUint8(1))) {
      (0x49, 0x49) => Endian.little,
      (0x4D, 0x4D) => Endian.big,
      _ => throw const FormatException('TIFF 바이트 순서가 아님'),
    };
    if (tiff.getUint16(2, endian) != 42) {
      throw const FormatException('TIFF 표지가 아님');
    }

    final ifd0 = tiff.getUint32(4, endian);
    final count = tiff.getUint16(ifd0, endian);
    // 항목들 뒤에 다음 IFD 위치(4바이트)가 온다.
    final ifd0End = ifd0 + 2 + count * 12 + 4;
    _checkRange(tiff, ifd0, ifd0End - ifd0);

    int? gpsEntry;
    for (var i = 0; i < count; i++) {
      final entry = ifd0 + 2 + i * 12;
      if (tiff.getUint16(entry, endian) == _gpsInfoTag) {
        gpsEntry = entry;
        break;
      }
    }
    if (gpsEntry == null) return segment;

    final gpsRanges = _gpsRanges(
      tiff,
      tiff.getUint32(gpsEntry + 8, endian),
      endian,
    );
    for (final (start, length) in gpsRanges) {
      if (start < ifd0End && ifd0 < start + length) {
        throw const FormatException('GPS 칸이 IFD0 와 겹침');
      }
    }

    // 뒤 항목과 다음 IFD 위치를 한 칸 당기고, 비는 끝 12바이트를 0 으로 둔다.
    copy.setRange(
      tiffStart + gpsEntry,
      tiffStart + ifd0End - 12,
      copy,
      tiffStart + gpsEntry + 12,
    );
    copy.fillRange(tiffStart + ifd0End - 12, tiffStart + ifd0End, 0);
    tiff.setUint16(ifd0, count - 1, endian);

    for (final (start, length) in gpsRanges) {
      copy.fillRange(tiffStart + start, tiffStart + start + length, 0);
    }
    return copy;
  } on RangeError {
    return null;
  } on FormatException {
    return null;
  }
}

/// GPS IFD 자신과, 4바이트를 넘어 따로 적힌 값들의 (시작, 길이) 목록
List<(int, int)> _gpsRanges(ByteData tiff, int offset, Endian endian) {
  final count = tiff.getUint16(offset, endian);
  final ranges = <(int, int)>[(offset, 2 + count * 12 + 4)];
  _checkRange(tiff, offset, 2 + count * 12 + 4);

  for (var i = 0; i < count; i++) {
    final entry = offset + 2 + i * 12;
    final typeSize = _tiffTypeSizes[tiff.getUint16(entry + 2, endian)];
    if (typeSize == null) throw const FormatException('모르는 TIFF 값 형식');

    final size = typeSize * tiff.getUint32(entry + 4, endian);
    if (size > 4) ranges.add((tiff.getUint32(entry + 8, endian), size));
  }

  for (final (start, length) in ranges) {
    _checkRange(tiff, start, length);
  }
  return ranges;
}

void _checkRange(ByteData data, int start, int length) {
  if (start < 0 || length < 0 || start + length > data.lengthInBytes) {
    throw RangeError('EXIF 칸이 조각 밖을 가리킴');
  }
}
