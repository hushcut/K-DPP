import 'dart:convert';
import 'dart:typed_data';

/// 시험용 위도·경도(RATIONAL 셋 = 분자·분모 여섯). 지운 뒤 바이트에 남지 않아야 한다.
const latitudeRationals = [37, 1, 33, 1, 1234, 100];
const longitudeRationals = [126, 1, 58, 1, 5678, 100];

/// 압축 데이터 흉내. 0xFF 0x00(바이트 채움)과 RST(0xFF 0xD0)가 들어 있어도 사진 끝으로 보면 안 된다.
const scanData = [0x12, 0xFF, 0x00, 0x34, 0xFF, 0xD0, 0x56];

/// RATIONAL 값들을 TIFF 바이트 순서대로 적은 바이트
Uint8List rationalBytes(List<int> values, Endian endian) {
  final data = ByteData(values.length * 4);
  for (var i = 0; i < values.length; i++) {
    data.setUint32(i * 4, values[i], endian);
  }
  return data.buffer.asUint8List();
}

/// IFD0(방향 · GPSInfo · PrintIM) → IFD1(압축 방식) → GPS IFD(위도·경도 참조와 값)를 담은 TIFF.
///
/// GPSInfo 뒤에 항목을 하나 더 두어, 항목을 당길 때 뒤 항목과 다음 IFD 위치가 함께 옮겨지는지 본다.
/// [gpsOffset]·[gpsValueType] 으로 깨진 EXIF 를 만든다.
Uint8List buildTiff({
  required Endian endian,
  bool withGps = true,
  int orientation = 6,
  int? gpsOffset,
  int gpsValueType = 5,
}) {
  final ifd0Count = withGps ? 3 : 2;
  const ifd0 = 8;
  final ifd1 = ifd0 + 2 + ifd0Count * 12 + 4;
  final gpsIfd = ifd1 + 2 + 12 + 4;
  final latitude = gpsIfd + 2 + 4 * 12 + 4;
  final longitude = latitude + 24;
  final data = ByteData(longitude + 24);

  data
    ..setUint8(0, endian == Endian.little ? 0x49 : 0x4D)
    ..setUint8(1, endian == Endian.little ? 0x49 : 0x4D)
    ..setUint16(2, 42, endian)
    ..setUint32(4, ifd0, endian);

  var entry = ifd0 + 2;
  void writeEntry(int tag, int type, int count, void Function(int) value) {
    data
      ..setUint16(entry, tag, endian)
      ..setUint16(entry + 2, type, endian)
      ..setUint32(entry + 4, count, endian);
    value(entry + 8);
    entry += 12;
  }

  data.setUint16(ifd0, ifd0Count, endian);
  writeEntry(0x0112, 3, 1, (at) => data.setUint16(at, orientation, endian));
  if (withGps) {
    writeEntry(
      0x8825,
      4,
      1,
      (at) => data.setUint32(at, gpsOffset ?? gpsIfd, endian),
    );
  }
  writeEntry(0xC4A5, 7, 4, (at) {
    for (var i = 0; i < 4; i++) {
      data.setUint8(at + i, 'TEST'.codeUnitAt(i));
    }
  });
  data.setUint32(entry, ifd1, endian);

  entry = ifd1 + 2;
  data.setUint16(ifd1, 1, endian);
  writeEntry(0x0103, 3, 1, (at) => data.setUint16(at, 6, endian));
  data.setUint32(entry, 0, endian);

  entry = gpsIfd + 2;
  data.setUint16(gpsIfd, 4, endian);
  writeEntry(0x0001, 2, 2, (at) => data.setUint8(at, 'N'.codeUnitAt(0)));
  writeEntry(
    0x0002,
    gpsValueType,
    3,
    (at) => data.setUint32(at, latitude, endian),
  );
  writeEntry(0x0003, 2, 2, (at) => data.setUint8(at, 'E'.codeUnitAt(0)));
  writeEntry(0x0004, 5, 3, (at) => data.setUint32(at, longitude, endian));
  data.setUint32(entry, 0, endian);

  final bytes = data.buffer.asUint8List();
  bytes.setAll(latitude, rationalBytes(latitudeRationals, endian));
  bytes.setAll(longitude, rationalBytes(longitudeRationals, endian));
  return bytes;
}

/// 표지와 길이를 붙인 JPEG 조각
Uint8List segment(int marker, List<int> payload) {
  final length = payload.length + 2;
  return Uint8List.fromList([
    0xFF,
    marker,
    length >> 8,
    length & 0xFF,
    ...payload,
  ]);
}

Uint8List exifSegment(Uint8List tiff) =>
    segment(0xE1, [...latin1.encode('Exif\x00\x00'), ...tiff]);

Uint8List xmpSegment(String body) => segment(0xE1, [
  ...latin1.encode('http://ns.adobe.com/xap/1.0/\x00'),
  ...utf8.encode(body),
]);

Uint8List mpfSegment() =>
    segment(0xE2, [...latin1.encode('MPF\x00'), 0x4D, 0x4D, 0x00, 0x2A]);

/// SOI → 머리 조각들 → SOS + 압축 데이터 → EOI → 끝에 붙은 데이터
Uint8List buildJpeg({
  List<Uint8List> headerSegments = const [],
  List<int> trailing = const [],
}) {
  return Uint8List.fromList([
    0xFF,
    0xD8,
    ...segment(0xE0, latin1.encode('JFIF\x00\x01\x01')),
    for (final header in headerSegments) ...header,
    ...segment(0xDA, [0x01, 0x01, 0x00, 0x00, 0x3F, 0x00]),
    ...scanData,
    0xFF,
    0xD9,
    ...trailing,
  ]);
}

bool containsBytes(List<int> haystack, List<int> needle) {
  for (var i = 0; i + needle.length <= haystack.length; i++) {
    var match = true;
    for (var j = 0; j < needle.length; j++) {
      if (haystack[i + j] != needle[j]) {
        match = false;
        break;
      }
    }
    if (match) return true;
  }
  return false;
}

/// 시험에서 확인할 EXIF 의 모양
class ExifSummary {
  const ExifSummary({
    required this.ifd0Tags,
    required this.orientation,
    required this.ifd1Compression,
    required this.gapBeforeIfd1,
  });

  final List<int> ifd0Tags;
  final int? orientation;

  /// 다음 IFD 위치를 따라가 읽은 IFD1 의 압축 방식. 위치가 어긋나면 엉뚱한 값이 나온다.
  final int? ifd1Compression;

  /// IFD0 끝과 IFD1 사이의 바이트. 항목을 하나 빼면 12바이트가 비어 0 이어야 한다.
  final List<int> gapBeforeIfd1;
}

/// JPEG 의 첫 EXIF 조각을 읽는다. EXIF 조각이 없으면 null.
ExifSummary? readExif(Uint8List jpeg) {
  final name = latin1.encode('Exif\x00\x00');
  var position = 2;
  while (position + 4 <= jpeg.length && jpeg[position + 1] != 0xDA) {
    // 표지 앞 채움 바이트(0xFF)
    if (jpeg[position + 1] == 0xFF) {
      position++;
      continue;
    }
    final length = (jpeg[position + 2] << 8) | jpeg[position + 3];
    final payload = jpeg.sublist(position + 4, position + 2 + length);
    if (jpeg[position + 1] == 0xE1 &&
        containsBytes(payload.take(6).toList(), name)) {
      final tiff = ByteData.sublistView(Uint8List.fromList(payload), 6);
      final endian = tiff.getUint8(0) == 0x49 ? Endian.little : Endian.big;
      final ifd0 = tiff.getUint32(4, endian);
      final count = tiff.getUint16(ifd0, endian);
      final tags = <int>[];
      int? orientation;
      for (var i = 0; i < count; i++) {
        final entry = ifd0 + 2 + i * 12;
        final tag = tiff.getUint16(entry, endian);
        tags.add(tag);
        if (tag == 0x0112) orientation = tiff.getUint16(entry + 8, endian);
      }
      final ifd0End = ifd0 + 2 + count * 12 + 4;
      final ifd1 = tiff.getUint32(ifd0End - 4, endian);
      final ifd1Compression = ifd1 == 0
          ? null
          : tiff.getUint16(ifd1 + 2 + 8, endian);
      return ExifSummary(
        ifd0Tags: tags,
        orientation: orientation,
        ifd1Compression: ifd1Compression,
        gapBeforeIfd1: ifd1 > ifd0End
            ? tiff.buffer.asUint8List(
                tiff.offsetInBytes + ifd0End,
                ifd1 - ifd0End,
              )
            : const [],
      );
    }
    position += 2 + length;
  }
  return null;
}
