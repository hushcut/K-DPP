import 'package:flutter/material.dart';

/// 소재 편집 한 행의 이름·함유율 입력과 두 필드의 포커스를 함께 관리합니다.
class MaterialEditController {
  MaterialEditController({required String name, required double percent})
    : nameController = TextEditingController(text: name),
      percentController = TextEditingController(text: _formatPercent(percent)),
      nameFocusNode = FocusNode(),
      percentFocusNode = FocusNode();

  // 소재명과 함유율 텍스트 필드에 연결되는 컨트롤러입니다.
  final TextEditingController nameController;
  final TextEditingController percentController;
  /// 소재명 필드가 사용하는 포커스 노드입니다.
  final FocusNode nameFocusNode;
  /// 함유율 필드가 사용하는 포커스 노드입니다. 키보드 위 막대를 띄울지 판단할 때 씁니다.
  final FocusNode percentFocusNode;

  /// 이 행이 보유한 Flutter 리소스를 모두 해제합니다.
  void dispose() {
    nameController.dispose();
    percentController.dispose();
    nameFocusNode.dispose();
    percentFocusNode.dispose();
  }

  static String _formatPercent(double value) {
    if (value % 1 == 0) {
      return value.toInt().toString();
    }

    return value.toStringAsFixed(1);
  }
}
