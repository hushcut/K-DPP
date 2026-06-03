import 'material_edit_controller.dart';

class MaterialInputCollection {
  final List<MaterialEditController> _items = [];

  bool get isEmpty => _items.isEmpty;

  int get length => _items.length;

  MaterialEditController operator [](int index) => _items[index];

  void setFromMaterials(Map<String, double> materials) {
    clear();

    materials.forEach((key, value) {
      _items.add(MaterialEditController(name: key, percent: value));
    });
  }

  void addEmpty() {
    _items.add(MaterialEditController(name: '', percent: 0));
  }

  void removeAt(int index) {
    final removed = _items.removeAt(index);
    removed.dispose();
  }

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
