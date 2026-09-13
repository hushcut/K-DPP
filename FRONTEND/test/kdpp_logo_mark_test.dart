import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/kdpp_logo_mark.dart';

class _MissingLogoBundle extends CachingAssetBundle {
  @override
  Future<ByteData> load(String key) {
    if (key.endsWith('kdpp_logo.png')) {
      throw FlutterError('Logo unavailable for fallback test');
    }
    return rootBundle.load(key);
  }
}

void main() {
  testWidgets('기본 접근성 이름은 한 번만 노출되고 null이면 생략된다', (tester) async {
    final semantics = tester.ensureSemantics();
    try {
      await tester.pumpWidget(const MaterialApp(home: KdppLogoMark()));
      expect(find.bySemanticsLabel('K-DPP'), findsOneWidget);
      await tester.pumpWidget(
        const MaterialApp(
          home: Column(
            children: [KdppLogoMark(semanticLabel: null), Text('K-DPP')],
          ),
        ),
      );
      expect(find.bySemanticsLabel('K-DPP'), findsOneWidget);
      expect(
        find.descendant(
          of: find.byType(KdppLogoMark),
          matching: find.byType(Semantics),
        ),
        findsNothing,
      );
    } finally {
      semantics.dispose();
    }
  });

  for (final size in [34.0, 96.0]) {
    testWidgets('자산 로딩 실패 시 ${size.toInt()}px 택·잎 모양과 투명 배경을 유지한다', (
      tester,
    ) async {
      final boundaryKey = GlobalKey();
      await tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: RepaintBoundary(
              key: boundaryKey,
              child: DefaultAssetBundle(
                bundle: _MissingLogoBundle(),
                child: KdppLogoMark(size: size),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.byType(CustomPaint), findsWidgets);

      // Compare the actual fallback raster to the exported source, allowing
      // different edge antialiasing between Flutter and the SVG renderer.
      await tester.runAsync(() async {
        final boundary =
            boundaryKey.currentContext!.findRenderObject()!
                as RenderRepaintBoundary;
        final actualImage = await boundary.toImage(pixelRatio: 1);
        final actual = (await actualImage.toByteData())!;
        final source = await rootBundle.load(KdppLogoMark.assetPath);
        final codec = await ui.instantiateImageCodec(
          source.buffer.asUint8List(source.offsetInBytes, source.lengthInBytes),
          targetWidth: size.toInt(),
          targetHeight: size.toInt(),
        );
        final expectedImage = (await codec.getNextFrame()).image;
        final expected = (await expectedImage.toByteData())!;
        var alphaError = 0;
        var greenIntersection = 0;
        var greenUnion = 0;
        bool isGreen(ByteData pixels, int at) =>
            pixels.getUint8(at + 3) > 200 &&
            pixels.getUint8(at + 1) > pixels.getUint8(at + 2) + 25;
        for (var at = 0; at < actual.lengthInBytes; at += 4) {
          alphaError += (actual.getUint8(at + 3) - expected.getUint8(at + 3))
              .abs();
          final a = isGreen(actual, at), b = isGreen(expected, at);
          if (a && b) greenIntersection++;
          if (a || b) greenUnion++;
        }
        expect(alphaError / (size * size * 255), lessThan(0.035));
        expect(greenUnion, greaterThan(0));
        expect(greenIntersection / greenUnion, greaterThan(0.80));
        expect(actual.getUint8(3), 0);
        final hole =
            ((size * .28).floor() * size.toInt() + (size * .50).floor()) * 4;
        expect(actual.getUint8(hole + 3), lessThan(20));
        actualImage.dispose();
        expectedImage.dispose();
        codec.dispose();
      });
    });
  }
}
