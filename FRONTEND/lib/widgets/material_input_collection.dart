import 'package:flutter/foundation.dart';

import 'material_edit_controller.dart';

/// 소재 편집 행의 컨트롤러들을 한곳에서 생성·수집·해제하는 컬렉션입니다.
///
/// [ChangeNotifier]로서 소재명·함유율 텍스트가 바뀌거나 행이 추가·삭제될 때
/// 알림을 보냅니다. 합계 표시처럼 입력에 반응해야 하는 위젯은 화면 전체를
/// 다시 그리는 대신 이 컬렉션을 구독해 필요한 부분만 갱신할 수 있습니다.
///
/// 항목 제거·전체 초기화·[dispose] 호출 시 각 [MaterialEditController.dispose]를 실행합니다.
class MaterialInputCollection extends ChangeNotifier {
  final List<MaterialEditController> _items = [];

  // 현재 편집할 소재가 없는지와 전체 행 수를 제공합니다.
  bool get isEmpty => _items.isEmpty;

  int get length => _items.length;

  /// 지정한 위치의 편집 컨트롤러를 반환합니다.
  MaterialEditController operator [](int index) => _items[index];

  /// 기존 행을 모두 해제하고 소재 맵의 값으로 편집 행을 다시 만듭니다.
  void setFromMaterials(Map<String, double> materials) {
    _clearItems();

    materials.forEach((key, value) {
      _addItem(MaterialEditController(name: key, percent: value));
    });

    notifyListeners();
  }

  /// 사용자가 새 소재를 입력할 수 있는 빈 행을 추가합니다.
  void addEmpty() {
    _addItem(MaterialEditController(name: '', percent: 0));
    notifyListeners();
  }

  /// 지정한 행을 제거하고 행이 보유한 컨트롤러도 해제합니다.
  void removeAt(int index) {
    _removeItem(index);
    notifyListeners();
  }

  /// 입력된 소재명과 함유율을 맵으로 반환하며, 같은 소재명은 비율을 합산합니다.
  Map<String, double> collectEditedMaterials() {
    final updated = <String, double>{};

    for (final item in _items) {
      final name = item.nameController.text.trim();
      final percentText = item.percentController.text.trim().replaceAll(
        '%',
        '',
      );

      if (name.isEmpty) continue;

      final parsed = double.tryParse(percentText) ?? 0.0;
      updated[name] = (updated[name] ?? 0) + parsed;
    }

    return updated;
  }

  /// 모든 편집 컨트롤러를 해제하고 컬렉션을 비웁니다.
  void clear() {
    _clearItems();
    notifyListeners();
  }

  void _addItem(MaterialEditController item) {
    item.nameController.addListener(notifyListeners);
    item.percentController.addListener(notifyListeners);
    _items.add(item);
  }

  void _removeItem(int index) {
    final removed = _items.removeAt(index);
    removed.nameController.removeListener(notifyListeners);
    removed.percentController.removeListener(notifyListeners);
    removed.dispose();
  }

  void _clearItems() {
    while (_items.isNotEmpty) {
      _removeItem(_items.length - 1);
    }
  }

  @override
  void dispose() {
    _clearItems();
    super.dispose();
  }
}
