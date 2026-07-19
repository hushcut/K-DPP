import 'material_edit_controller.dart';

/// 소재 편집 행의 컨트롤러들을 한곳에서 생성·수집·해제하는 컬렉션입니다.
///
/// 항목 제거·전체 초기화·[dispose] 호출 시 각 [MaterialEditController.dispose]를 실행합니다.
class MaterialInputCollection {
  final List<MaterialEditController> _items = [];

  // 현재 편집할 소재가 없는지와 전체 행 수를 제공합니다.
  bool get isEmpty => _items.isEmpty;

  int get length => _items.length;

  /// 지정한 위치의 편집 컨트롤러를 반환합니다.
  MaterialEditController operator [](int index) => _items[index];

  /// 기존 행을 모두 해제하고 소재 맵의 값으로 편집 행을 다시 만듭니다.
  void setFromMaterials(Map<String, double> materials) {
    clear();

    materials.forEach((key, value) {
      _items.add(MaterialEditController(name: key, percent: value));
    });
  }

  /// 사용자가 새 소재를 입력할 수 있는 빈 행을 추가합니다.
  void addEmpty() {
    _items.add(MaterialEditController(name: '', percent: 0));
  }

  /// 지정한 행을 제거하고 행이 보유한 컨트롤러도 해제합니다.
  void removeAt(int index) {
    final removed = _items.removeAt(index);
    removed.dispose();
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
    for (final item in _items) {
      item.dispose();
    }

    _items.clear();
  }

  void dispose() {
    clear();
  }
}
