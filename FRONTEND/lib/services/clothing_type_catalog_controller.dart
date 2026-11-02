import 'package:flutter/foundation.dart';

import '../models/clothing_type_option.dart';
import '../utils/clothing_type_catalog.dart';

/// 의류 종류 선택에 쓸 무게표를 서버 우선으로 제공합니다.
///
/// 처음에는 앱 내장 표([ClothingTypeCatalog.options])를 값으로 갖고 있어 바로 고를 수 있고,
/// 서버 표를 받으면 목록을 바꿔 알립니다. 서버 표 뒤에는 앱의 '직접 입력' 항목을 붙입니다.
/// 받지 못하면 내장 표를 그대로 두고, 다음 [load] 호출에서 다시 요청합니다.
/// 받은 표는 기기에 저장하지 않습니다(DECISIONS 2026-09-16).
class ClothingTypeCatalogController
    extends ValueNotifier<List<ClothingTypeOption>> {
  ClothingTypeCatalogController({
    required Future<List<ClothingTypeOption>> Function() fetchClothingTypes,
  }) : _fetchClothingTypes = fetchClothingTypes,
       super(ClothingTypeCatalog.options);

  final Future<List<ClothingTypeOption>> Function() _fetchClothingTypes;

  bool _isLoading = false;
  bool _isServerLoaded = false;
  bool _isDisposed = false;

  /// 지금 목록이 서버에서 받은 표인지 알려 줍니다.
  bool get isServerLoaded => _isServerLoaded;

  /// 아직 서버 표를 받지 못했을 때만 요청합니다. 요청 중이거나 이미 받았으면 무시합니다.
  Future<void> load() async {
    if (_isLoading || _isServerLoaded) return;

    _isLoading = true;

    try {
      final serverOptions = await _fetchClothingTypes();
      if (_isDisposed) return;

      _isServerLoaded = true;
      value = List.unmodifiable([
        ...serverOptions,
        ...ClothingTypeCatalog.options.where(
          (option) => option.isDirectWeightPlaceholder,
        ),
      ]);
    } catch (error, stackTrace) {
      if (_isDisposed) return;

      // 앱 내장 표가 이미 값이라 사용자 흐름은 끊기지 않습니다.
      debugPrint('의류 무게표를 서버에서 받지 못해 앱 내장 표를 씁니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    } finally {
      _isLoading = false;
    }
  }

  @override
  void dispose() {
    _isDisposed = true;
    super.dispose();
  }
}
