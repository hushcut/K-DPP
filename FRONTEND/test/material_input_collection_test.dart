import 'package:flutter_test/flutter_test.dart';
import 'package:k_dpp/widgets/material_input_collection.dart';

void main() {
  group('MaterialInputCollection', () {
    test('setFromMaterials creates editable material inputs', () {
      final collection = MaterialInputCollection();
      addTearDown(collection.dispose);

      collection.setFromMaterials({'cotton': 80, 'polyester': 20});

      expect(collection.length, 2);
      expect(collection.collectEditedMaterials(), {
        'cotton': 80,
        'polyester': 20,
      });
    });

    test('collectEditedMaterials ignores empty material names', () {
      final collection = MaterialInputCollection();
      addTearDown(collection.dispose);

      collection.addEmpty();
      collection[0].percentController.text = '30';

      expect(collection.collectEditedMaterials(), isEmpty);
    });

    test('collectEditedMaterials sums duplicate material names', () {
      final collection = MaterialInputCollection();
      addTearDown(collection.dispose);

      collection.addEmpty();
      collection[0].nameController.text = 'cotton';
      collection[0].percentController.text = '60';

      collection.addEmpty();
      collection[1].nameController.text = 'cotton';
      collection[1].percentController.text = '40%';

      expect(collection.collectEditedMaterials(), {'cotton': 100});
    });

    test('removeAt removes selected material input', () {
      final collection = MaterialInputCollection();
      addTearDown(collection.dispose);

      collection.setFromMaterials({'cotton': 70, 'nylon': 30});

      collection.removeAt(0);

      expect(collection.length, 1);
      expect(collection.collectEditedMaterials(), {'nylon': 30});
    });
  });
}
