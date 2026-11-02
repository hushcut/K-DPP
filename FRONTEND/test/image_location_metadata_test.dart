import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/image_location_metadata.dart';

import 'helpers/jpeg_with_location.dart';

// 2026-10-23: 앨범 사진(image_picker)은 원본의 EXIF 를 그대로 붙여, 촬영 위치가 서버와
// Google Vision 으로 갔다. 서버는 방향 값이 1 이 아닐 때만 EXIF 를 버린다.
void main() {
  for (final endian in [Endian.little, Endian.big]) {
    final order = endian == Endian.little ? 'II' : 'MM';

    test('[$order] GPS 칸을 지우고 방향 값과 다른 칸은 남긴다', () {
      final original = buildJpeg(
        headerSegments: [exifSegment(buildTiff(endian: endian))],
      );

      final stripped = stripLocationMetadata(original);
      final exif = readExif(stripped)!;

      expect(exif.ifd0Tags, [0x0112, 0xC4A5]);
      expect(exif.orientation, 6);
      expect(exif.ifd1Compression, 6, reason: '다음 IFD 위치가 함께 옮겨져야 한다');
      expect(exif.gapBeforeIfd1, List.filled(12, 0), reason: '빈 자리는 0 으로 덮는다');
      expect(
        containsBytes(stripped, rationalBytes(latitudeRationals, endian)),
        isFalse,
      );
      expect(
        containsBytes(stripped, rationalBytes(longitudeRationals, endian)),
        isFalse,
      );
      expect(stripped.length, original.length, reason: 'EXIF 는 제자리에서 덮는다');
      expect(containsBytes(stripped, [...scanData, 0xFF, 0xD9]), isTrue);
    });
  }

  test('GPS 가 없으면 받은 바이트를 그대로 돌려준다', () {
    final original = buildJpeg(
      headerSegments: [
        exifSegment(buildTiff(endian: Endian.big, withGps: false)),
        xmpSegment(
          '<x:xmpmeta><rdf:Description tiff:Orientation="6"/></x:xmpmeta>',
        ),
      ],
    );

    expect(stripLocationMetadata(original), same(original));
  });

  test('JPEG 가 아니면 그대로 둔다', () {
    final png = Uint8List.fromList([
      0x89,
      0x50,
      0x4E,
      0x47,
      0x0D,
      0x0A,
      0x1A,
      0x0A,
      0x00,
      0x00,
    ]);

    expect(stripLocationMetadata(png), same(png));
    expect(stripLocationMetadata(Uint8List(0)), isEmpty);
  });

  test('GPS 가 적힌 XMP 조각은 빼고, 없는 XMP 조각은 남긴다', () {
    const withGps =
        '<x:xmpmeta><rdf:Description exif:GPSLatitude="37,33.2N"/></x:xmpmeta>';
    const withoutGps =
        '<x:xmpmeta><rdf:Description xmp:Rating="0"/></x:xmpmeta>';
    final original = buildJpeg(
      headerSegments: [xmpSegment(withGps), xmpSegment(withoutGps)],
    );

    final stripped = stripLocationMetadata(original);

    expect(containsBytes(stripped, utf8.encode('GPSLatitude')), isFalse);
    expect(containsBytes(stripped, utf8.encode(withoutGps)), isTrue);
    expect(containsBytes(stripped, [...scanData, 0xFF, 0xD9]), isTrue);
  });

  test('사진 끝 뒤에 붙은 데이터와 MPF 목록을 뺀다', () {
    final movie = [
      ...latin1.encode('ftypmp42'),
      ...latin1.encode('©xyz+37.55+126.97/'),
    ];
    final original = buildJpeg(
      headerSegments: [mpfSegment()],
      trailing: [0xFF, 0xD8, 0xFF, 0xE1, ...movie],
    );

    final stripped = stripLocationMetadata(original);

    expect(stripped.sublist(stripped.length - 2), [0xFF, 0xD9]);
    expect(containsBytes(stripped, latin1.encode('ftypmp42')), isFalse);
    expect(containsBytes(stripped, latin1.encode('MPF\x00')), isFalse);
    expect(
      containsBytes(stripped, [...scanData, 0xFF, 0xD9]),
      isTrue,
      reason: '압축 데이터 안의 0xFF 0x00·RST 를 사진 끝으로 보면 안 된다',
    );
  });

  test('표지 앞 채움 바이트(0xFF)가 있어도 뒤 조각을 읽는다', () {
    final tiff = buildTiff(endian: Endian.little);
    final original = buildJpeg(
      headerSegments: [
        Uint8List.fromList([0xFF, ...exifSegment(tiff)]),
      ],
    );

    final stripped = stripLocationMetadata(original);

    expect(readExif(stripped)?.orientation, 6);
    expect(readExif(stripped)?.ifd0Tags, [0x0112, 0xC4A5]);
    expect(
      containsBytes(stripped, rationalBytes(latitudeRationals, Endian.little)),
      isFalse,
    );
  });

  group('EXIF 를 안전하게 읽지 못하면 위치를 남기지 않도록 EXIF 조각을 뺀다', () {
    void expectExifRemoved(Uint8List tiff) {
      final original = buildJpeg(headerSegments: [exifSegment(tiff)]);

      final stripped = stripLocationMetadata(original);

      expect(readExif(stripped), isNull);
      expect(
        containsBytes(stripped, rationalBytes(latitudeRationals, Endian.big)),
        isFalse,
      );
      expect(containsBytes(stripped, [...scanData, 0xFF, 0xD9]), isTrue);
    }

    test('GPS 칸 위치가 조각 밖', () {
      expectExifRemoved(buildTiff(endian: Endian.big, gpsOffset: 0xFFFF));
    });

    test('GPS 칸이 IFD0 와 겹침', () {
      expectExifRemoved(buildTiff(endian: Endian.big, gpsOffset: 8));
    });

    test('GPS 값의 형식을 모름', () {
      expectExifRemoved(buildTiff(endian: Endian.big, gpsValueType: 99));
    });

    test('TIFF 바이트 순서 표지가 아님', () {
      final tiff = buildTiff(endian: Endian.big)..setAll(0, [0x00, 0x00]);
      expectExifRemoved(tiff);
    });
  });
}
