import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'services/auth_api_service.dart';
import 'theme_provider.dart';
import 'widgets/app_back_button.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, this.authApiService});

  final AuthApiService? authApiService;

  String _themeModeLabel(ThemeMode mode) {
    switch (mode) {
      case ThemeMode.dark:
        return '블랙';
      case ThemeMode.light:
        return '화이트';
      case ThemeMode.system:
        return '시스템 설정';
    }
  }

  Future<void> _editNickname(BuildContext context, String currentName) async {
    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => _NicknameEditDialog(currentName: currentName),
    );

    if (result == null) return;

    if (!context.mounted) return;

    final normalizedName = result.trim();

    if (normalizedName == currentName.trim()) return;

    await context.read<ClosetProvider>().setUserName(normalizedName);

    if (!context.mounted) return;

    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('이 기기에 표시되는 닉네임이 변경되었습니다.')));
  }

  Future<void> _confirmLogout(BuildContext context) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: const Text('로그아웃'),
          content: const Text('로그아웃 하시겠어요?', style: TextStyle(height: 1.5)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext, false),
              child: const Text('취소'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(dialogContext, true),
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF4A4EFE),
              ),
              child: const Text('로그아웃', style: TextStyle(color: Colors.white)),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    if (!context.mounted) return;

    final provider = context.read<ClosetProvider>();
    final accessToken = provider.accessToken;
    String? serverLogoutError;
    bool localLogoutStorageFailed = false;

    if (accessToken != null) {
      try {
        await (authApiService ?? AuthApiService()).logout(
          accessToken: accessToken,
        );
      } on AuthApiException catch (error) {
        serverLogoutError = error.userMessage;
      }
    }

    try {
      await provider.logout();
    } catch (error, stackTrace) {
      localLogoutStorageFailed = true;
      debugPrint('로그아웃 정보 정리 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    if (!context.mounted) return;

    Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);

    if (serverLogoutError != null || localLogoutStorageFailed) {
      final message = localLogoutStorageFailed
          ? '기기에서는 로그아웃되었지만 저장된 로그인 정보 정리를 완료하지 못했습니다.'
          : '기기에서는 로그아웃되었지만 서버 연결에 실패했습니다. $serverLogoutError';

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    }
  }

  void _showComingSoon(BuildContext context, String title) {
    showDialog<void>(
      context: context,
      builder: (dialogContext) {
        return AlertDialog(
          title: Text(title),
          content: const Text(
            '아직 준비 중인 기능이에요. 업데이트 후 사용할 수 있어요.',
            style: TextStyle(height: 1.5),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('확인'),
            ),
          ],
        );
      },
    );
  }

  void _showPrivacyGuide(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final backgroundColor = isDark ? const Color(0xFF121212) : Colors.white;
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF5F6368);

    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      backgroundColor: backgroundColor,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (sheetContext) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(24, 8, 24, 28),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  '사진 및 권한 안내',
                  style: TextStyle(
                    color: primaryText,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 14),
                _buildPrivacyGuideRow(
                  icon: Icons.camera_alt_outlined,
                  text: '카메라는 스캔 화면에서만 켜지고, 다른 화면에서는 사용하지 않습니다.',
                  textColor: secondaryText,
                ),
                _buildPrivacyGuideRow(
                  icon: Icons.delete_outline,
                  text: '카메라로 새로 촬영한 임시 파일은 분석이 끝난 뒤 정리합니다.',
                  textColor: secondaryText,
                ),
                _buildPrivacyGuideRow(
                  icon: Icons.photo_library_outlined,
                  text: '앨범에서 선택한 원본 사진은 앱이 수정하지 않습니다.',
                  textColor: secondaryText,
                ),
                _buildPrivacyGuideRow(
                  icon: Icons.cloud_done_outlined,
                  text: '서버 분석이 연결된 경우 이미지는 라벨 분석 요청에만 사용됩니다.',
                  textColor: secondaryText,
                ),
                const SizedBox(height: 18),
                SizedBox(
                  width: double.infinity,
                  height: 48,
                  child: ElevatedButton(
                    onPressed: () => Navigator.pop(sheetContext),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF4A4EFE),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text(
                      '확인했어요',
                      style: TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildPrivacyGuideRow({
    required IconData icon,
    required String text,
    required Color textColor,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: const Color(0xFF4A4EFE), size: 21),
          const SizedBox(width: 12),
          Expanded(
            child: Text(
              text,
              style: TextStyle(color: textColor, fontSize: 14, height: 1.5),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionTitle(String title, Color color) {
    return Padding(
      padding: const EdgeInsets.only(left: 4, bottom: 10),
      child: Text(
        title,
        style: TextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w700,
          color: color,
        ),
      ),
    );
  }

  Widget _buildMenuTile({
    required IconData icon,
    required String title,
    String? subtitle,
    Color iconColor = const Color(0xFF4A4EFE),
    Color textColor = const Color(0xFF111111),
    Color subtitleColor = const Color(0xFF8C8C8C),
    VoidCallback? onTap,
    bool showChevron = true,
  }) {
    return ListTile(
      contentPadding: const EdgeInsets.symmetric(horizontal: 18, vertical: 6),
      minLeadingWidth: 20,
      leading: Icon(icon, color: iconColor, size: 22),
      title: Text(
        title,
        style: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: textColor,
        ),
      ),
      subtitle: subtitle == null
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(
                subtitle,
                style: TextStyle(
                  fontSize: 13,
                  color: subtitleColor,
                  height: 1.4,
                ),
              ),
            ),
      trailing: showChevron
          ? Icon(Icons.chevron_right, color: subtitleColor)
          : null,
      onTap: onTap,
    );
  }

  Widget _buildCard(List<Widget> children, Color background, Color border) {
    return Container(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: border),
      ),
      child: Column(children: children),
    );
  }

  @override
  Widget build(BuildContext context) {
    final userName = context.watch<ClosetProvider>().userName;
    final userEmail = context.watch<ClosetProvider>().userEmail;
    final themeMode = context.watch<ThemeProvider>().themeMode;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    final backgroundColor = isDark
        ? const Color(0xFF121212)
        : const Color(0xFFF8F9FC);
    final cardColor = isDark ? const Color(0xFF1C1C1E) : Colors.white;
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFEAEAEA);
    final primaryText = isDark ? Colors.white : const Color(0xFF111111);
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF5F6368);
    final sectionText = isDark
        ? const Color(0xFF9A9A9A)
        : const Color(0xFF8E8E93);
    final profileBoxColor = isDark
        ? const Color(0xFF2A2A2E)
        : const Color(0xFFEEF1FF);

    return Scaffold(
      backgroundColor: backgroundColor,
      appBar: AppBar(
        backgroundColor: backgroundColor,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: true,
        automaticallyImplyLeading: false,
        leadingWidth: 52,
        leading: const Padding(
          padding: EdgeInsets.only(left: 8),
          child: AppBackButton(),
        ),
        title: Text(
          '설정',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          Container(
            padding: const EdgeInsets.all(22),
            decoration: BoxDecoration(
              color: cardColor,
              borderRadius: BorderRadius.circular(28),
              border: Border.all(color: borderColor),
            ),
            child: Row(
              children: [
                Container(
                  width: 62,
                  height: 62,
                  decoration: BoxDecoration(
                    color: profileBoxColor,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Icon(
                    Icons.person_outline,
                    color: Color(0xFF4A4EFE),
                    size: 30,
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        userName,
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w700,
                          color: primaryText,
                        ),
                      ),
                      const SizedBox(height: 6),
                      Text(
                        userEmail,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 14,
                          color: secondaryText,
                          height: 1.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 28),

          _buildSectionTitle('내 정보', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.person_outline,
                title: '닉네임',
                subtitle: userName,
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _editNickname(context, userName),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.mail_outline,
                title: '이메일',
                subtitle: userEmail,
                textColor: primaryText,
                subtitleColor: secondaryText,
                showChevron: false,
              ),
            ],
            cardColor,
            borderColor,
          ),
          const SizedBox(height: 24),

          _buildSectionTitle('앱 설정', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.dark_mode_outlined,
                title: '화면 설정',
                subtitle: _themeModeLabel(themeMode),
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () {
                  Navigator.pushNamed(context, '/display-settings');
                },
              ),
            ],
            cardColor,
            borderColor,
          ),
          const SizedBox(height: 24),

          _buildSectionTitle('개인정보', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.privacy_tip_outlined,
                title: '사진 및 권한 안내',
                subtitle: '스캔에 사용하는 카메라와 사진 처리 방식을 확인합니다.',
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _showPrivacyGuide(context),
              ),
            ],
            cardColor,
            borderColor,
          ),
          const SizedBox(height: 24),

          _buildSectionTitle('계정 관리', sectionText),
          _buildCard(
            [
              _buildMenuTile(
                icon: Icons.lock_outline,
                title: '비밀번호 변경',
                subtitle: '비밀번호를 다시 설정합니다.',
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _showComingSoon(context, '비밀번호 변경'),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.logout,
                title: '로그아웃',
                subtitle: '현재 계정에서 로그아웃합니다.',
                textColor: primaryText,
                subtitleColor: secondaryText,
                onTap: () => _confirmLogout(context),
              ),
              Divider(height: 1, color: borderColor),
              _buildMenuTile(
                icon: Icons.person_remove_outlined,
                title: '회원 탈퇴',
                subtitle: '계정을 삭제합니다.',
                iconColor: Colors.redAccent,
                textColor: Colors.redAccent,
                subtitleColor: secondaryText,
                onTap: () => _showComingSoon(context, '회원 탈퇴'),
              ),
            ],
            cardColor,
            borderColor,
          ),
        ],
      ),
    );
  }
}

class _NicknameEditDialog extends StatefulWidget {
  const _NicknameEditDialog({required this.currentName});

  final String currentName;

  @override
  State<_NicknameEditDialog> createState() => _NicknameEditDialogState();
}

class _NicknameEditDialogState extends State<_NicknameEditDialog> {
  late final TextEditingController _controller;
  String? _errorText;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.currentName);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final normalizedName = _controller.text.trim();

    if (normalizedName.length < 2) {
      setState(() {
        _errorText = '닉네임은 2자 이상 입력해 주세요.';
      });
      return;
    }

    Navigator.pop(context, normalizedName);
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return AlertDialog(
      title: const Text('닉네임 수정'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        textInputAction: TextInputAction.done,
        autofillHints: const [AutofillHints.nickname],
        style: TextStyle(
          color: isDark ? Colors.white : const Color(0xFF111111),
        ),
        decoration: InputDecoration(
          labelText: '닉네임',
          hintText: '예: 홍길동',
          errorText: _errorText,
          hintStyle: TextStyle(
            color: isDark ? const Color(0xFF9A9A9A) : const Color(0xFF5F6368),
          ),
          filled: true,
          fillColor: isDark ? const Color(0xFF2A2A2E) : const Color(0xFFF1F1F4),
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 18,
            vertical: 16,
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: BorderSide.none,
          ),
        ),
        onChanged: (_) {
          if (_errorText == null) return;
          setState(() {
            _errorText = null;
          });
        },
        onSubmitted: (_) => _submit(),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('취소'),
        ),
        ElevatedButton(
          onPressed: _submit,
          style: ElevatedButton.styleFrom(
            backgroundColor: const Color(0xFF4A4EFE),
          ),
          child: const Text('저장', style: TextStyle(color: Colors.white)),
        ),
      ],
    );
  }
}
