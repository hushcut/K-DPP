import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/services/material_catalog_api_service.dart';
import 'package:k_dpp/services/material_catalog_controller.dart';

void main() {
  const cotton = MaterialCatalogItem(
    id: 1,
    nameKo: '면',
    nameEn: 'cotton',
    aliases: ['코튼'],
  );

  test('처음 불러오면 불러오는 중을 거쳐 목록을 받는다', () async {
    final response = Completer<List<MaterialCatalogItem>>();
    final catalog = MaterialCatalogController(
      fetchMaterials: () => response.future,
    );
    addTearDown(catalog.dispose);

    expect(catalog.status, MaterialCatalogStatus.idle);

    final loading = catalog.load();
    expect(catalog.status, MaterialCatalogStatus.loading);

    response.complete(const [cotton]);
    await loading;

    expect(catalog.status, MaterialCatalogStatus.loaded);
    expect(catalog.items, const [cotton]);
  });

  test('불러오는 중이거나 이미 받은 목록이면 다시 요청하지 않는다', () async {
    final response = Completer<List<MaterialCatalogItem>>();
    var fetchCount = 0;
    final catalog = MaterialCatalogController(
      fetchMaterials: () {
        fetchCount++;
        return response.future;
      },
    );
    addTearDown(catalog.dispose);

    final first = catalog.load();
    final second = catalog.load();
    response.complete(const [cotton]);
    await Future.wait([first, second]);
    await catalog.load();

    expect(fetchCount, 1);
  });

  test('실패하면 실패 상태가 되고, 다시 불러오면 다시 요청한다', () async {
    final originalDebugPrint = debugPrint;
    debugPrint = (String? message, {int? wrapWidth}) {};
    addTearDown(() => debugPrint = originalDebugPrint);

    var fetchCount = 0;
    final catalog = MaterialCatalogController(
      fetchMaterials: () async {
        fetchCount++;
        if (fetchCount == 1) throw Exception('network');
        return const [cotton];
      },
    );
    addTearDown(catalog.dispose);

    await catalog.load();
    expect(catalog.status, MaterialCatalogStatus.failed);
    expect(catalog.items, isEmpty);

    await catalog.load();
    expect(fetchCount, 2);
    expect(catalog.status, MaterialCatalogStatus.loaded);
    expect(catalog.items, const [cotton]);
  });

  test('해제된 뒤에 응답이 와도 오류 없이 무시한다', () async {
    final response = Completer<List<MaterialCatalogItem>>();
    final catalog = MaterialCatalogController(
      fetchMaterials: () => response.future,
    );

    final loading = catalog.load();
    catalog.dispose();
    response.complete(const [cotton]);

    await expectLater(loading, completes);
  });
}
