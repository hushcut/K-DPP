// 의류 삭제 확인, Provider 저장 반영과 화면 복귀 동작을 처리합니다.
part of '../report_screen.dart';

/// 삭제 확인 후 Provider에서 제거하고 변경사항을 저장한 뒤 호출 화면으로 복귀합니다.
Future<void> _confirmDelete(
  BuildContext context,
  Clothes item, {
  VoidCallback? onDeleted,
}) async {
  final isDark = Theme.of(context).brightness == Brightness.dark;

  final confirmed = await showDialog<bool>(
    context: context,
    builder: (dialogContext) {
      return AlertDialog(
        backgroundColor: isDark ? const Color(0xFF1C1C1E) : Colors.white,
        title: Text(
          '의류 삭제',
          style: TextStyle(
            color: isDark ? Colors.white : const Color(0xFF111111),
          ),
        ),
        content: Text(
          '"${item.title}"을(를) 삭제할까요?\n이 작업은 되돌릴 수 없습니다.',
          style: TextStyle(
            height: 1.5,
            color: isDark ? const Color(0xFFD1D1D6) : const Color(0xFF444444),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.redAccent,
            ),
            child: const Text('삭제', style: TextStyle(color: Colors.white)),
          ),
        ],
      );
    },
  );

  if (confirmed != true) return;

  if (!context.mounted) return;

  await context.read<ClosetProvider>().removeClothes(item);

  if (!context.mounted) return;

  ScaffoldMessenger.of(
    context,
  ).showSnackBar(SnackBar(content: Text('"${item.title}"이(가) 삭제되었습니다.')));

  if (onDeleted != null) {
    onDeleted();
    return;
  }

  Navigator.pushReplacementNamed(context, '/main', arguments: 2);
}
