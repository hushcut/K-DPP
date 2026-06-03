import 'package:flutter/material.dart';

class MaterialEditController {
  MaterialEditController({required String name, required double percent})
    : nameController = TextEditingController(text: name),
      percentController = TextEditingController(text: _formatPercent(percent));

  final TextEditingController nameController;
  final TextEditingController percentController;

  void dispose() {
    nameController.dispose();
    percentController.dispose();
  }

  static String _formatPercent(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}
