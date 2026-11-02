import 'package:flutter/foundation.dart';

import 'material_catalog_api_service.dart';

/// 서버 소재 카탈로그를 불러오는 진행 상태입니다.
enum MaterialCatalogStatus { idle, loading, loaded, failed }

/// 서버 소재 카탈로그를 한 번 불러와 보관하고, 실패하면 다시 불러올 수 있게 합니다.
///
/// 결과 화면의 소재 추천 목록과 소재 선택창이 같은 목록·상태를 보도록 한곳에 둡니다.
/// 선택창이 열려 있는 동안 불러오기가 끝나도 바로 반영되도록 변경을 알립니다.
class MaterialCatalogController extends ChangeNotifier {
  MaterialCatalogController({
    required Future<List<MaterialCatalogItem>> Function() fetchMaterials,
  }) : _fetchMaterials = fetchMaterials;

  final Future<List<MaterialCatalogItem>> Function() _fetchMaterials;

  List<MaterialCatalogItem> _items = const [];
  MaterialCatalogStatus _status = MaterialCatalogStatus.idle;
  bool _isDisposed = false;

  List<MaterialCatalogItem> get items => _items;
  MaterialCatalogStatus get status => _status;

  /// 아직 불러오지 않았거나 실패한 경우에만 요청합니다.
  /// 불러오는 중이거나 이미 받은 목록은 다시 요청하지 않습니다.
  Future<void> load() async {
    if (_status == MaterialCatalogStatus.loading ||
        _status == MaterialCatalogStatus.loaded) {
      return;
    }

    _status = MaterialCatalogStatus.loading;
    notifyListeners();

    try {
      final items = await _fetchMaterials();
      if (_isDisposed) return;

      _items = items;
      _status = MaterialCatalogStatus.loaded;
    } catch (error, stackTrace) {
      if (_isDisposed) return;

      // 일시적인 실패가 앱 사용 내내 목록을 막지 않도록, 다음 스캔이나
      // 선택창의 '다시 불러오기'에서 다시 요청할 수 있게 둡니다.
      _status = MaterialCatalogStatus.failed;
      debugPrint('소재 자동완성 목록을 불러오지 못했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    notifyListeners();
  }

  @override
  void dispose() {
    _isDisposed = true;
    super.dispose();
  }
}
