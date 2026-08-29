// 의류 이름·분류·세탁 지침을 수정하는 하단 시트를 관리합니다.
part of '../report_screen.dart';

/// 편집 시트에서 받은 복사본을 Provider의 원본 항목과 교체합니다.
Future<void> _showEditBottomSheet(
  BuildContext context,
  Clothes item,
) async {
  final updated = await showModalBottomSheet<Clothes>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    backgroundColor: Theme.of(context).brightness == Brightness.dark
        ? const Color(0xFF121212)
        : Colors.white,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
    ),
    builder: (sheetContext) {
      return _ReportEditSheet(item: item);
    },
  );

  if (updated == null) return;

  if (!context.mounted) return;

  final bool success;

  try {
    success = await context.read<ClosetProvider>().updateClothes(item, updated);
  } catch (_) {
    // 저장 실패 시 Provider가 이전 값으로 되돌리므로 재시도만 안내합니다.
    if (!context.mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('수정 내용을 저장하지 못했어요. 다시 시도해 주세요.')),
    );
    return;
  }

  if (!context.mounted) return;

  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(success ? '의류 정보가 수정되었습니다.' : '수정할 의류를 찾지 못했습니다.'),
    ),
  );
}

/// 이름·분류·세탁 지침만 수정하고 분석된 소재·탄소 값은 유지하는 하단 시트입니다.
class _ReportEditSheet extends StatefulWidget {
  const _ReportEditSheet({required this.item});

  final Clothes item;

  @override
  State<_ReportEditSheet> createState() => _ReportEditSheetState();
}

class _ReportEditSheetState extends State<_ReportEditSheet> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  late final TextEditingController _titleController;
  late final TextEditingController _careController;
  late final List<String> _categoryOptions;
  late String _category;

  @override
  void initState() {
    super.initState();
    _titleController = TextEditingController(text: widget.item.title);
    _careController = TextEditingController(text: widget.item.careInstruction);
    _categoryOptions = [
      '상의',
      '하의',
      if (widget.item.category != '상의' && widget.item.category != '하의')
        widget.item.category,
    ];
    _category = _categoryOptions.contains(widget.item.category)
        ? widget.item.category
        : '상의';
  }

  @override
  void dispose() {
    _titleController.dispose();
    _careController.dispose();
    super.dispose();
  }

  // 원본을 직접 변경하지 않고 copyWith로 수정본을 만들어 호출 화면에 돌려줍니다.
  void _submit() {
    final isValid = _formKey.currentState?.validate() ?? false;

    if (!isValid) return;

    Navigator.pop(
      context,
      widget.item.copyWith(
        title: _titleController.text.trim(),
        category: _category,
        careInstruction: _careController.text.trim(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;
    final inputFillColor = isDark ? const Color(0xFF2A2A2E) : Colors.white;

    return SafeArea(
      top: false,
      child: AnimatedPadding(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
        padding: EdgeInsets.only(
          bottom: MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 28),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '의류 정보 수정',
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 22,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  '이름, 분류, 라벨 지침을 수정할 수 있어요. 소재와 탄소 계산값은 유지됩니다.',
                  style: TextStyle(
                    color: secondaryText,
                    fontSize: 13,
                    height: 1.5,
                  ),
                ),
                const SizedBox(height: 18),
                TextFormField(
                  controller: _titleController,
                  validator: ScanFormValidator.validateTitle,
                  textInputAction: TextInputAction.next,
                  style: TextStyle(color: primaryText),
                  decoration: InputDecoration(
                    filled: true,
                    fillColor: inputFillColor,
                    labelText: '의류 이름',
                    hintText: '예: 코튼 맨투맨',
                    labelStyle: TextStyle(color: secondaryText),
                    hintStyle: TextStyle(color: secondaryText),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    prefixIcon: const Icon(Icons.checkroom_outlined),
                  ),
                ),
                const SizedBox(height: 14),
                DropdownButtonFormField<String>(
                  initialValue: _category,
                  items: _categoryOptions
                      .map(
                        (category) => DropdownMenuItem(
                          value: category,
                          child: Text(category),
                        ),
                      )
                      .toList(),
                  dropdownColor: inputFillColor,
                  style: TextStyle(color: primaryText),
                  decoration: InputDecoration(
                    filled: true,
                    fillColor: inputFillColor,
                    labelText: '분류',
                    labelStyle: TextStyle(color: secondaryText),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    prefixIcon: const Icon(Icons.category_outlined),
                  ),
                  onChanged: (value) {
                    if (value == null) return;

                    setState(() {
                      _category = value;
                    });
                  },
                ),
                const SizedBox(height: 14),
                TextFormField(
                  controller: _careController,
                  minLines: 3,
                  maxLines: 5,
                  style: TextStyle(color: primaryText),
                  decoration: InputDecoration(
                    filled: true,
                    fillColor: inputFillColor,
                    labelText: '세탁 지침',
                    hintText: '예: 찬물 세탁 후 자연 건조',
                    alignLabelWithHint: true,
                    labelStyle: TextStyle(color: secondaryText),
                    hintStyle: TextStyle(color: secondaryText),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    prefixIcon: const Padding(
                      padding: EdgeInsets.only(bottom: 56),
                      child: Icon(Icons.local_laundry_service_outlined),
                    ),
                  ),
                ),
                const SizedBox(height: 22),
                SizedBox(
                  width: double.infinity,
                  height: 50,
                  child: ElevatedButton(
                    onPressed: _submit,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: AppPalette.accent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text(
                      '수정 완료',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
