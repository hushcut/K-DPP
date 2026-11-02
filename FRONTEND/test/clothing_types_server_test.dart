import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:k_dpp/models/clothing_type_option.dart';
import 'package:k_dpp/services/clothing_type_catalog_api_service.dart';
import 'package:k_dpp/services/clothing_type_catalog_controller.dart';
import 'package:k_dpp/utils/clothing_type_catalog.dart';
import 'package:k_dpp/widgets/clothing_type_picker_sheet.dart';

/// 의류 무게표는 서버 `GET /clothing-types`를 먼저 쓰고, 받지 못하면 앱 내장 표를 쓴다
/// (DECISIONS 2026-09-13 회의 ②, 2026-09-16 세부).
void main() {
  Map<String, dynamic> serverItem({
    String id = 'knit',
    String label = '니트',
    String category = '상의',
    Object? min = 400,
    Object? max = 900,
    Object? estimated = 620,
  }) {
    return {
      'id': id,
      'label': label,
      'category': category,
      'min_weight_grams': min,
      'max_weight_grams': max,
      'estimated_weight_grams': estimated,
    };
  }

  group('서버 항목 검사', () {
    test('숫자 무게를 그대로 쓰고 문구·아이콘을 만든다', () {
      final option = ClothingTypeOption.fromServerJson(
        serverItem(min: 410.5, max: 910, estimated: 630),
      )!;

      expect(option.id, 'knit');
      expect(option.minWeightGram, 410.5);
      expect(option.maxWeightGram, 910);
      expect(option.estimatedWeightGram, 630);
      expect(option.weightRangeLabel, '410.5~910g');
      expect(option.icon, Icons.texture_outlined);
      expect(option.isDirectWeight, isFalse);
      expect(option.isDirectWeightPlaceholder, isFalse);
    });

    test('계산에 쓰기에 이상한 항목은 받아들이지 않는다', () {
      final rejected = <String, Map<String, dynamic>>{
        '식별자 없음': serverItem(id: ''),
        '이름 없음': serverItem(label: ' '),
        '옷장 탭에 없는 분류': serverItem(category: '신발'),
        '무게가 글자': serverItem(min: '400'),
        '무게 누락': serverItem(max: null),
        '0 무게': serverItem(min: 0),
        '음수 무게': serverItem(estimated: -1),
        '대표 무게가 최소보다 작음': serverItem(estimated: 300),
        '대표 무게가 최대보다 큼': serverItem(estimated: 1000),
        '최소가 최대보다 큼': serverItem(min: 950, max: 900, estimated: 920),
        '무한대': serverItem(max: double.infinity),
      };

      rejected.forEach((reason, json) {
        expect(ClothingTypeOption.fromServerJson(json), isNull, reason: reason);
      });
    });

    test('모르는 식별자는 기본 옷 아이콘을 쓴다', () {
      final option = ClothingTypeOption.fromServerJson(
        serverItem(id: 'hanbok', label: '한복'),
      )!;

      expect(option.icon, Icons.checkroom_outlined);
    });
  });

  group('서버 무게표 요청', () {
    // 한글 본문은 문자 집합을 밝혀야 가짜 응답을 만들 수 있다.
    http.Response jsonResponse(Object body, int statusCode) {
      return http.Response.bytes(
        utf8.encode(jsonEncode(body)),
        statusCode,
        headers: {'content-type': 'application/json; charset=utf-8'},
      );
    }

    Future<List<ClothingTypeOption>> fetchWith(http.Response response) {
      final client = MockClient((_) async => response);
      addTearDown(client.close);
      return ClothingTypeCatalogApiService(client: client).fetchClothingTypes();
    }

    test('/clothing-types의 items를 서버 순서대로 받고 이상한 항목만 뺀다', () async {
      late http.Request captured;
      final client = MockClient((request) async {
        captured = request;
        return http.Response(
          jsonEncode({
            'status': 'success',
            'source': 'backend',
            'unit': 'g',
            'items': [
              serverItem(id: 'outer', label: '아우터', min: 800, max: 1800, estimated: 1200),
              serverItem(id: 'broken', estimated: 5000),
              serverItem(id: 'pants', label: '바지', category: '하의', min: 450, max: 900, estimated: 680),
            ],
          }),
          200,
          headers: {'content-type': 'application/json; charset=utf-8'},
        );
      });
      addTearDown(client.close);

      final options = await ClothingTypeCatalogApiService(
        client: client,
      ).fetchClothingTypes();

      expect(captured.method, 'GET');
      expect(captured.url.path, '/clothing-types');
      expect(options.map((option) => option.id), ['outer', 'pants']);
    });

    test('실패 응답·다른 형식·쓸 항목 없음은 예외로 알린다', () async {
      await expectLater(
        fetchWith(jsonResponse({'detail': 'x'}, 500)),
        throwsA(isA<HttpException>()),
      );
      await expectLater(
        fetchWith(jsonResponse([serverItem()], 200)),
        throwsA(isA<FormatException>()),
      );
      await expectLater(
        fetchWith(
          jsonResponse({
            'items': [serverItem(estimated: 5000)],
          }, 200),
        ),
        throwsA(isA<FormatException>()),
      );
    });
  });

  group('무게표 목록 관리', () {
    final serverOptions = [
      ClothingTypeOption.fromServerJson(
        serverItem(id: 'knit', label: '니트', min: 420, max: 880, estimated: 640),
      )!,
    ];

    test('처음에는 앱 내장 표이고, 서버 표를 받으면 바꾸고 직접 입력을 뒤에 붙인다', () async {
      final response = Completer<List<ClothingTypeOption>>();
      final catalog = ClothingTypeCatalogController(
        fetchClothingTypes: () => response.future,
      );
      addTearDown(catalog.dispose);
      var notified = 0;
      catalog.addListener(() => notified++);

      expect(catalog.value, same(ClothingTypeCatalog.options));
      expect(catalog.isServerLoaded, isFalse);

      final loading = catalog.load();
      response.complete(serverOptions);
      await loading;

      expect(catalog.isServerLoaded, isTrue);
      expect(notified, 1);
      expect(catalog.value, hasLength(2));
      expect(catalog.value.first.minWeightGram, 420);
      expect(catalog.value.last.isDirectWeightPlaceholder, isTrue);
    });

    test('받지 못하면 앱 내장 표를 그대로 두고, 다음 요청에서 다시 받는다', () async {
      var calls = 0;
      final catalog = ClothingTypeCatalogController(
        fetchClothingTypes: () async {
          calls++;
          if (calls == 1) throw const SocketException('오프라인');
          return serverOptions;
        },
      );
      addTearDown(catalog.dispose);

      await catalog.load();
      expect(catalog.value, same(ClothingTypeCatalog.options));
      expect(catalog.isServerLoaded, isFalse);

      await catalog.load();
      expect(calls, 2);
      expect(catalog.isServerLoaded, isTrue);
    });

    test('받는 중이거나 이미 받았으면 다시 요청하지 않는다', () async {
      final response = Completer<List<ClothingTypeOption>>();
      var calls = 0;
      final catalog = ClothingTypeCatalogController(
        fetchClothingTypes: () {
          calls++;
          return response.future;
        },
      );
      addTearDown(catalog.dispose);

      final first = catalog.load();
      await catalog.load();
      response.complete(serverOptions);
      await first;
      await catalog.load();

      expect(calls, 1);
    });

    test('화면이 사라진 뒤 도착한 응답은 무시한다', () async {
      final response = Completer<List<ClothingTypeOption>>();
      final catalog = ClothingTypeCatalogController(
        fetchClothingTypes: () => response.future,
      );

      final loading = catalog.load();
      catalog.dispose();
      response.complete(serverOptions);

      await expectLater(loading, completes);
    });
  });

  group('선택창이 열린 동안 서버 표 도착', () {
    testWidgets('목록이 서버 값으로 바뀌고, 고른 종류 표시는 유지되며, 고르면 서버 값이 나온다', (
      tester,
    ) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 2.625;
      addTearDown(tester.view.reset);

      final response = Completer<List<ClothingTypeOption>>();
      final catalog = ClothingTypeCatalogController(
        fetchClothingTypes: () => response.future,
      );
      addTearDown(catalog.dispose);
      final knit = ClothingTypeCatalog.options.firstWhere(
        (option) => option.id == 'knit',
      );
      ClothingTypeOption? picked;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () async {
                  picked = await showClothingTypePickerSheet(
                    context: context,
                    options: catalog.value,
                    optionsListenable: catalog,
                    initialSelection: knit,
                  );
                },
                child: const Text('시트 열기'),
              ),
            ),
          ),
        ),
      );
      unawaited(catalog.load());
      await tester.tap(find.text('시트 열기'));
      await tester.pumpAndSettle();

      expect(find.text('상의 · 예상 무게 400~900g'), findsOneWidget);

      response.complete([
        ClothingTypeOption.fromServerJson(
          serverItem(id: 'knit', label: '니트', min: 420, max: 880, estimated: 640),
        )!,
      ]);
      await tester.pumpAndSettle();

      expect(find.text('상의 · 예상 무게 400~900g'), findsNothing);
      expect(find.text('상의 · 예상 무게 420~880g'), findsOneWidget);
      // 이름으로 선택 표시를 맞추므로 목록이 바뀌어도 니트가 선택된 채다.
      expect(
        find.descendant(
          of: find.ancestor(
            of: find.text('니트'),
            matching: find.byType(InkWell),
          ),
          matching: find.byIcon(Icons.check_circle),
        ),
        findsOneWidget,
      );

      await tester.tap(find.text('니트'));
      await tester.pumpAndSettle();

      expect(picked?.minWeightGram, 420);
      expect(picked?.maxWeightGram, 880);
    });
  });
}
