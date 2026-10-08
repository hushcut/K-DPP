// 프로필 표시값, 화면 테마, 개인정보 안내와 계정 관리(로그아웃·비밀번호 변경·회원 탈퇴)를
// 제공하는 설정 화면입니다.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'closet_provider.dart';
import 'material_name_display_provider.dart';
import 'services/auth_api_service.dart';
import 'services/kakao_login_service.dart';
import 'theme/app_palette.dart';
import 'theme_provider.dart';
import 'utils/accessibility_announcer.dart';
import 'utils/session_expiry_handler.dart';
import 'widgets/app_back_button.dart';
import 'widgets/app_banner.dart';
import 'widgets/kakao_login_button.dart';

/// 사용자·테마 상태를 읽어 설정 메뉴를 구성하고 각 설정 동작을 실행합니다.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({
    super.key,
    this.authApiService,
    this.kakaoLoginService,
  });

  final AuthApiService? authApiService;

  /// 카카오 계정의 탈퇴 확인(재로그인)과 로그아웃·탈퇴 뒤 기기의 카카오 토큰 지우기에 씁니다.
  final KakaoLoginService? kakaoLoginService;

  /// 카카오 계정이면 기기에 저장된 카카오 SDK 토큰을 지웁니다(DECISIONS 183 ⑤).
  ///
  /// 기다리지 않습니다 — 카카오가 늦어도 로그아웃·탈퇴 화면이 멈추지 않게. SDK 는 요청이
  /// 끝날 때 토큰을 지우고, [KakaoLoginService.signOut] 은 실패를 밖으로 내지 않습니다.
  void _signOutKakaoIfNeeded(bool isKakaoAccount) {
    if (!isKakaoAccount) return;
    unawaited((kakaoLoginService ?? KakaoLoginService()).signOut());
  }

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

  /// 닉네임 편집 대화상자의 결과가 달라졌을 때만 Provider와 로컬 저장소를 갱신합니다.
  Future<void> _editNickname(BuildContext context, String currentName) async {
    final result = await showDialog<String>(
      context: context,
      builder: (dialogContext) => _NicknameEditDialog(currentName: currentName),
    );

    if (result == null) return;

    if (!context.mounted) return;

    final normalizedName = result.trim();

    if (normalizedName == currentName.trim()) return;

    try {
      await context.read<ClosetProvider>().setUserName(normalizedName);
    } catch (_) {
      // 저장 실패 시 Provider가 이전 닉네임으로 되돌리므로 재시도만 안내합니다.
      if (!context.mounted) return;

      AppBanner.of(context).show(
        '닉네임을 저장하지 못했어요. 다시 시도해 주세요.',
        kind: AppBannerKind.failure,
      );
      return;
    }

    if (!context.mounted) return;

    AppBanner.of(context).show(
      '이 기기에 표시되는 닉네임이 바뀌었어요.',
      kind: AppBannerKind.success,
    );
  }

  /// 서버 로그아웃을 시도한 뒤 성공 여부와 관계없이 기기의 세션·사용자 상태를 정리합니다.
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
                backgroundColor: AppPalette.accent,
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
    final isKakaoAccount = provider.loginMethods.contains(LoginMethod.kakao);
    bool serverLogoutFailed = false;
    bool localLogoutStorageFailed = false;

    // 서버 로그아웃은 최대 15초까지 걸립니다. 그동안 설정 화면이 그대로 눌리면
    // 사용자가 로그아웃을 다시 누르거나, 곧 폐기될 토큰으로 회원 탈퇴를 시작할 수
    // 있습니다. 그 탈퇴 요청은 401을 받아 탈퇴되지 않은 채 로그인 화면으로 넘어가므로,
    // 사용자는 비밀번호까지 입력한 탈퇴를 처음부터 다시 해야 합니다.
    final navigator = Navigator.of(context);
    var isProgressVisible = true;

    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => const _BlockingProgressDialog(
          message: '로그아웃 중이에요…',
        ),
      ),
    );

    void dismissProgress() {
      if (!isProgressVisible) return;
      isProgressVisible = false;
      navigator.pop();
    }

    if (accessToken != null) {
      // 서버 연결 실패는 기록하되 기기에서 로그아웃하는 흐름은 계속 진행합니다.
      try {
        await (authApiService ?? AuthApiService()).logout(
          accessToken: accessToken,
        );
      } on AuthApiException {
        serverLogoutFailed = true;
      }
    }

    _signOutKakaoIfNeeded(isKakaoAccount);

    try {
      await provider.logout();
    } catch (error, stackTrace) {
      localLogoutStorageFailed = true;
      debugPrint('로그아웃 정보 정리 중 오류가 발생했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    dismissProgress();

    if (!context.mounted) return;

    Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);

    if (serverLogoutFailed || localLogoutStorageFailed) {
      // 서버 오류 안내를 이어 붙이면 세 문장까지 길어져 붙이지 않는다(DECISIONS 98).
      final message = localLogoutStorageFailed
          ? '로그아웃했어요. 일부 정보는 정리하지 못했어요.'
          : '로그아웃했어요. 서버에는 연결하지 못했어요.';

      // 로그아웃은 됐지만 일부가 안 됐으므로 실패로 알린다.
      AppBanner.of(context).show(message, kind: AppBannerKind.failure);
    }
  }

  /// 비밀번호 변경 대화상자를 띄우고, 성공 시 서버가 재발급한 토큰으로 세션을 갱신합니다.
  ///
  /// 요청 자체는 대화상자가 수행합니다. 그래야 진행 중에 화면을 벗어날 수 없고,
  /// 서버가 거절해도 입력을 잃지 않은 채 해당 필드에 오류를 보여 줄 수 있습니다.
  Future<void> _changePassword(BuildContext context) async {
    final provider = context.read<ClosetProvider>();
    final accessToken = provider.accessToken;

    if (accessToken == null) {
      await SessionExpiryHandler.handle(context);
      return;
    }

    final outcome = await showDialog<_AccountActionResult>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => _PasswordChangeDialog(
        service: authApiService ?? AuthApiService(),
        accessToken: accessToken,
      ),
    );

    if (outcome == null) return;

    if (!context.mounted) return;

    if (outcome.sessionExpiredMessage case final message?) {
      await SessionExpiryHandler.handle(context, message: message);
      return;
    }

    final banner = AppBanner.of(context);
    final result = outcome.authResult;
    final newAccessToken = result?.accessToken;
    final expiresInSeconds = result?.expiresInSeconds;

    if (result == null || newAccessToken == null || expiresInSeconds == null) {
      // 서버가 기존 토큰을 이미 폐기했으므로 이 기기 세션도 더는 쓸 수 없습니다.
      await SessionExpiryHandler.handle(
        context,
        message: '비밀번호는 바뀌었어요. 다시 로그인해 주세요.',
      );
      return;
    }

    try {
      await provider.setAuthenticatedUser(
        nickname: result.user.nickname,
        email: result.user.email,
        userId: result.user.id,
        loginMethods: result.user.loginMethods,
        accessToken: newAccessToken,
        expiresInSeconds: expiresInSeconds,
      );
    } catch (error, stackTrace) {
      debugPrint('비밀번호 변경 후 세션 저장에 실패했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);

      if (!context.mounted) return;
      await SessionExpiryHandler.handle(
        context,
        message: '비밀번호는 바뀌었어요. 다시 로그인해 주세요.',
      );
      return;
    }

    if (!context.mounted) return;

    banner.show(
      '비밀번호가 바뀌었어요. 다른 기기에서는 다시 로그인해야 해요.',
      kind: AppBannerKind.success,
    );
  }

  /// 탈퇴 대화상자를 띄우고, 서버 삭제가 끝난 뒤에만 기기에 남은 계정 데이터를 정리합니다.
  Future<void> _confirmWithdraw(BuildContext context) async {
    final provider = context.read<ClosetProvider>();
    final accessToken = provider.accessToken;

    if (accessToken == null) {
      await SessionExpiryHandler.handle(context);
      return;
    }

    final isKakaoAccount = provider.loginMethods.contains(LoginMethod.kakao);

    final outcome = await showDialog<_AccountActionResult>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) => _WithdrawDialog(
        service: authApiService ?? AuthApiService(),
        accessToken: accessToken,
        // 비밀번호가 없는 계정(카카오)은 비밀번호 대신 카카오 재로그인으로 확인합니다.
        kakaoLoginService: provider.hasPasswordLogin
            ? null
            : kakaoLoginService ?? KakaoLoginService(),
      ),
    );

    if (outcome == null) return;

    if (!context.mounted) return;

    // 401은 탈퇴가 끝났다는 증거가 아니므로 로그아웃만 합니다. 앞선 시도의 결과를
    // 아는 대화상자가 문구를 정하고, 계정이 남아 있을 수 있어 옷장은 지우지 않습니다.
    if (outcome.sessionExpiredMessage case final message?) {
      await SessionExpiryHandler.handle(
        context,
        message: message,
        kind: AppBannerKind.failure,
      );
      return;
    }

    bool localPurgeFailed = false;

    // 서버가 카카오 연결을 이미 끊었으니 기기에 남은 카카오 토큰도 쓸모가 없습니다.
    _signOutKakaoIfNeeded(isKakaoAccount);

    try {
      await provider.purgeAccountData();
    } catch (error, stackTrace) {
      localPurgeFailed = true;
      debugPrint('탈퇴 후 기기 데이터 정리에 실패했습니다: $error');
      debugPrintStack(stackTrace: stackTrace);
    }

    if (!context.mounted) return;

    Navigator.pushNamedAndRemoveUntil(context, '/login', (route) => false);

    final message = localPurgeFailed
        ? '회원 탈퇴가 완료됐어요. 이 기기의 일부 정보는 정리하지 못했어요.'
        : '회원 탈퇴가 완료됐어요.';

    AppBanner.of(context).show(
      message,
      kind: localPurgeFailed ? AppBannerKind.failure : AppBannerKind.success,
    );
  }

  // 카메라·앨범 사진과 임시 파일이 어떻게 사용되는지 하단 시트로 안내합니다.
  void _showPrivacyGuide(BuildContext context) {
    // 배경색은 테마(AppTheme.bottomSheetTheme)에 맡기고 글자색은 builder 안에서 읽습니다.
    // 여는 순간에 정하면 시트가 열린 채 시스템 밝기가 바뀔 때 따라오지 않습니다.
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (sheetContext) {
        final palette = AppPalette.of(sheetContext);
        final primaryText = palette.textPrimary;
        final secondaryText = palette.textSecondary;

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
                      backgroundColor: AppPalette.accent,
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
          Icon(icon, color: AppPalette.accent, size: 21),
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
    Color iconColor = AppPalette.accent,
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

  // 카드 색을 Container 로 칠하면 안의 ListTile 누름 효과가 그 아래에 그려져 보이지 않으므로,
  // 카드 전용 Material 위에 Ink 로 칠해 효과가 위에 보이게 하고 둥근 모서리 밖은 잘라 냅니다.
  Widget _buildCard(List<Widget> children, Color background, Color border) {
    return Material(
      color: Colors.transparent,
      borderRadius: BorderRadius.circular(24),
      clipBehavior: Clip.antiAlias,
      child: Ink(
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(24),
          border: Border.all(color: border),
        ),
        child: Column(children: children),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    // 사용자와 테마 Provider를 구독해 변경된 닉네임·화면 모드를 즉시 표시합니다.
    final userName = context.watch<ClosetProvider>().userName;
    // 이메일이 없는 계정(카카오)은 기본 이메일 대신 로그인 방법을 보여 줍니다.
    final accountEmail = context.watch<ClosetProvider>().accountEmail;
    final accountLabel = accountEmail ?? '카카오 계정';
    // 비밀번호가 없는 계정(카카오)은 바꿀 비밀번호가 없습니다(서버도 400 PASSWORD_NOT_SET).
    final hasPasswordLogin = context.watch<ClosetProvider>().hasPasswordLogin;
    final themeMode = context.watch<ThemeProvider>().themeMode;
    final materialNameDisplay = context
        .watch<MaterialNameDisplayProvider>()
        .display;
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    final backgroundColor = palette.background;
    final cardColor = palette.card;
    final borderColor = isDark
        ? const Color(0xFF2C2C2E)
        : const Color(0xFFEAEAEA);
    final primaryText = palette.textPrimary;
    final secondaryText = palette.textSecondary;
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
                    color: AppPalette.accent,
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
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          // 이메일이 없는 계정은 카카오 계정이므로 로그인 버튼과 같은 표식을 붙입니다.
                          if (accountEmail == null) ...[
                            const KakaoSymbolBadge(),
                            const SizedBox(width: 6),
                          ],
                          Flexible(
                            child: Text(
                              accountLabel,
                              maxLines: 2,
                              overflow: TextOverflow.ellipsis,
                              style: TextStyle(
                                fontSize: 14,
                                color: secondaryText,
                                height: 1.4,
                              ),
                            ),
                          ),
                        ],
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
                icon: accountEmail == null
                    ? Icons.login_outlined
                    : Icons.mail_outline,
                title: accountEmail == null ? '로그인' : '이메일',
                subtitle: accountLabel,
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
                subtitle:
                    '${_themeModeLabel(themeMode)} · 소재 이름 ${materialNameDisplay.label}',
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
              if (hasPasswordLogin) ...[
                _buildMenuTile(
                  icon: Icons.lock_outline,
                  title: '비밀번호 변경',
                  subtitle: '비밀번호를 다시 설정합니다.',
                  textColor: primaryText,
                  subtitleColor: secondaryText,
                  onTap: () => _changePassword(context),
                ),
                Divider(height: 1, color: borderColor),
              ],
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
                onTap: () => _confirmWithdraw(context),
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

/// 닉네임을 입력받아 최소 길이를 검사하고 정규화된 문자열을 반환하는 대화상자입니다.
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

  // 검증을 통과한 값만 Navigator 결과로 상위 설정 화면에 전달합니다.
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
    final palette = AppPalette.of(context);

    return AlertDialog(
      title: const Text('닉네임 수정'),
      content: TextField(
        controller: _controller,
        autofocus: true,
        textInputAction: TextInputAction.done,
        autofillHints: const [AutofillHints.nickname],
        style: TextStyle(color: palette.textPrimary),
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
            backgroundColor: AppPalette.accent,
          ),
          child: const Text('저장', style: TextStyle(color: Colors.white)),
        ),
      ],
    );
  }
}

/// 계정 관리 대화상자가 상위 화면으로 넘기는 결과입니다.
///
/// 대화상자가 스스로 처리할 수 없는 두 가지만 올려 보냅니다.
/// 성공(비밀번호 변경은 재발급 토큰 포함), 그리고 세션 만료(401).
class _AccountActionResult {
  const _AccountActionResult({this.authResult, this.sessionExpiredMessage});

  final AuthResult? authResult;
  final String? sessionExpiredMessage;
}

/// 계정 관리 대화상자가 공유하는 요청 수행 로직입니다.
///
/// 요청을 화면이 아니라 대화상자에서 수행하는 이유:
/// - 진행 중에는 대화상자를 닫을 수 없어 요청이 화면 없이 끝나는 경우가 없습니다.
/// - 서버가 거절해도 입력을 유지한 채 해당 필드에 오류를 보여 줄 수 있습니다.
/// - 버튼을 비활성화해 연타로 같은 요청이 중복 전송되지 않습니다.
mixin _AccountActionRunner<T extends StatefulWidget> on State<T> {
  bool _isSubmitting = false;

  bool get isSubmitting => _isSubmitting;

  /// 요청을 한 번만 실행하고, 실패 메시지를 대화상자에 표시하도록 돌려줍니다.
  ///
  /// 401만 상위 화면으로 올려 세션 만료로 처리하고 나머지 오류는 여기서 보여 줍니다.
  /// [describeFailure] 를 주면 서버 오류의 문구를 그 대화상자에 맞게 고릅니다.
  Future<void> runAccountAction({
    required Future<_AccountActionResult> Function() action,
    required void Function(String message) onFailure,
    String Function(AuthApiException error)? describeFailure,
  }) async {
    if (_isSubmitting) return;

    setState(() => _isSubmitting = true);

    try {
      final result = await action();

      if (!mounted) return;

      Navigator.pop(context, result);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      if (error.type == AuthApiErrorType.unauthorized) {
        Navigator.pop(
          context,
          _AccountActionResult(sessionExpiredMessage: error.userMessage),
        );
        return;
      }

      setState(() {
        _isSubmitting = false;
      });
      onFailure(describeFailure?.call(error) ?? error.userMessage);
    } catch (error) {
      if (!mounted) return;

      setState(() {
        _isSubmitting = false;
      });
      onFailure('요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    }
  }
}

/// 현재·새 비밀번호를 입력받아 검사하고 변경 요청까지 수행하는 대화상자입니다.
///
/// 서버(main.py `ensure_password_rules`)와 규칙이 어긋나면 사용자가 왕복 후에야
/// 오류를 보게 되므로, 8자 이상·앞뒤 공백 금지 두 규칙을 그대로 맞춥니다.
class _PasswordChangeDialog extends StatefulWidget {
  const _PasswordChangeDialog({
    required this.service,
    required this.accessToken,
  });

  final AuthApiService service;
  final String accessToken;

  @override
  State<_PasswordChangeDialog> createState() => _PasswordChangeDialogState();
}

class _PasswordChangeDialogState extends State<_PasswordChangeDialog>
    with _AccountActionRunner {
  final TextEditingController _currentController = TextEditingController();
  final TextEditingController _newController = TextEditingController();
  final TextEditingController _confirmController = TextEditingController();

  String? _currentError;
  String? _newError;
  String? _confirmError;

  @override
  void dispose() {
    _currentController.dispose();
    _newController.dispose();
    _confirmController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (isSubmitting) return;

    final current = _currentController.text;
    final next = _newController.text;
    final confirm = _confirmController.text;

    String? currentError;
    String? newError;
    String? confirmError;

    if (current.isEmpty) {
      currentError = '현재 비밀번호를 입력해 주세요.';
    }

    if (next.isEmpty) {
      newError = '새 비밀번호를 입력해 주세요.';
    } else if (next != next.trim()) {
      newError = '비밀번호 앞뒤에는 공백을 사용할 수 없습니다.';
    } else if (next.length < 8) {
      newError = '비밀번호는 8자 이상 입력해 주세요.';
    } else if (next == current) {
      newError = '새 비밀번호가 기존 비밀번호와 같습니다.';
    }

    if (confirm != next) {
      confirmError = '새 비밀번호가 일치하지 않습니다.';
    }

    if (currentError != null || newError != null || confirmError != null) {
      setState(() {
        _currentError = currentError;
        _newError = newError;
        _confirmError = confirmError;
      });
      return;
    }

    await runAccountAction(
      action: () async {
        final result = await widget.service.changePassword(
          accessToken: widget.accessToken,
          currentPassword: current,
          newPassword: next,
        );
        return _AccountActionResult(authResult: result);
      },
      // 서버 거절은 대부분 현재 비밀번호 불일치이므로 그 필드에 붙여 둡니다.
      onFailure: (message) => setState(() => _currentError = message),
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !isSubmitting,
      child: AlertDialog(
        title: const Text('비밀번호 변경'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _PasswordField(
                controller: _currentController,
                label: '현재 비밀번호',
                errorText: _currentError,
                autofocus: true,
                enabled: !isSubmitting,
                autofillHints: const [AutofillHints.password],
                onChanged: () {
                  if (_currentError == null) return;
                  setState(() => _currentError = null);
                },
              ),
              const SizedBox(height: 12),
              _PasswordField(
                controller: _newController,
                label: '새 비밀번호',
                helperText: '8자 이상, 앞뒤 공백 없이',
                errorText: _newError,
                enabled: !isSubmitting,
                autofillHints: const [AutofillHints.newPassword],
                onChanged: () {
                  if (_newError == null) return;
                  setState(() => _newError = null);
                },
              ),
              const SizedBox(height: 12),
              _PasswordField(
                controller: _confirmController,
                label: '새 비밀번호 확인',
                errorText: _confirmError,
                enabled: !isSubmitting,
                autofillHints: const [AutofillHints.newPassword],
                textInputAction: TextInputAction.done,
                onSubmitted: _submit,
                onChanged: () {
                  if (_confirmError == null) return;
                  setState(() => _confirmError = null);
                },
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: isSubmitting ? null : () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: isSubmitting ? null : _submit,
            style: ElevatedButton.styleFrom(backgroundColor: AppPalette.accent),
            child: isSubmitting
                ? const _SubmitProgress()
                : const Text('변경', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }
}

/// 되돌릴 수 없는 작업임을 알리고 비밀번호를 확인받아 탈퇴를 수행하는 대화상자입니다.
class _WithdrawDialog extends StatefulWidget {
  const _WithdrawDialog({
    required this.service,
    required this.accessToken,
    this.kakaoLoginService,
  });

  final AuthApiService service;
  final String accessToken;

  /// 있으면 비밀번호 대신 카카오계정 재로그인으로 확인합니다(비밀번호가 없는 카카오 계정).
  final KakaoLoginService? kakaoLoginService;

  @override
  State<_WithdrawDialog> createState() => _WithdrawDialogState();
}

class _WithdrawDialogState extends State<_WithdrawDialog>
    with _AccountActionRunner {
  final TextEditingController _passwordController = TextEditingController();
  String? _errorText;

  /// 앞선 탈퇴 요청이 서버에서 처리됐는지 모르는 채 끝난 적이 있는지 여부입니다.
  ///
  /// 400 계열(비밀번호 불일치·잠금·카카오 확인 실패)과 카카오의 502·503 은 서버가 삭제 전에
  /// 거절한 것이지만, 네트워크·시간 초과·그 밖의 서버 오류는 삭제를 마친 뒤 응답만 잃었을
  /// 수도 있습니다.
  bool _earlierAttemptUnresolved = false;

  /// 카카오계정 재로그인 화면이 떠 있는지입니다. 그동안도 대화상자를 닫거나 다시 누를 수 없습니다.
  bool _isKakaoSigningIn = false;

  bool get _isBusy => isSubmitting || _isKakaoSigningIn;

  bool get _usesKakao => widget.kakaoLoginService != null;

  @override
  void dispose() {
    _passwordController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (_isBusy) return;

    final password = _passwordController.text;

    if (password.isEmpty) {
      setState(() => _errorText = '비밀번호를 입력해 주세요.');
      return;
    }

    await _withdraw(
      () => widget.service.withdraw(
        accessToken: widget.accessToken,
        password: password,
      ),
    );
  }

  /// 카카오계정 로그인을 다시 해 받은 새 토큰으로 탈퇴를 확인합니다. 로그인 때 받아 SDK 에
  /// 저장된 토큰을 쓰면 사용자 입력 없이 탈퇴되므로 늘 새로 받습니다(SCAN_API_CONTRACT 2-3).
  Future<void> _submitWithKakao() async {
    if (_isBusy) return;

    setState(() {
      _isKakaoSigningIn = true;
      _errorText = null;
    });

    final String? kakaoAccessToken;

    try {
      kakaoAccessToken = await widget.kakaoLoginService!.reauthenticate();
    } on KakaoLoginException catch (error) {
      debugPrint('탈퇴 확인용 카카오 로그인을 마치지 못했습니다: ${error.cause}');

      if (!mounted) return;

      setState(() => _isKakaoSigningIn = false);
      _showKakaoError(error.userMessage);
      return;
    }

    if (!mounted) return;

    setState(() => _isKakaoSigningIn = false);

    // 카카오 화면에서 취소하면 대화상자를 그대로 둡니다.
    if (kakaoAccessToken == null) return;

    await _withdraw(
      () => widget.service.withdrawWithKakao(
        accessToken: widget.accessToken,
        kakaoAccessToken: kakaoAccessToken!,
      ),
    );
  }

  /// 카카오 확인에는 입력란이 없어 오류 문장을 따로 읽어 줍니다(입력란 오류처럼).
  void _showKakaoError(String message) {
    setState(() => _errorText = message);
    announceFieldError(context, message);
  }

  /// 삭제 전에 서버가 거절한 오류인지 — 그러면 다음 401 은 '진행되지 않음'입니다.
  static bool _rejectedBeforeDeletion(AuthApiException error) {
    // 카카오 502·503 은 상태 코드가 아니라 error_code 로 봅니다. 본문 없는 프록시 502 는
    // 결과를 모르는 서버 오류입니다.
    return error.type == AuthApiErrorType.badRequest ||
        error.errorCode == AuthErrorCode.socialProviderUnavailable ||
        error.errorCode == AuthErrorCode.socialLoginUnavailable;
  }

  static String _describeFailure(AuthApiException error) {
    return switch (error.errorCode) {
      AuthErrorCode.socialProviderUnavailable =>
        '카카오가 응답하지 않아 탈퇴되지 않았어요. 잠시 후 다시 시도해 주세요.',
      AuthErrorCode.socialLoginUnavailable => '지금은 카카오로 확인할 수 없어 탈퇴되지 않았어요.',
      _ => error.userMessage,
    };
  }

  Future<void> _withdraw(Future<void> Function() request) async {
    await runAccountAction(
      action: () async {
        try {
          await request();
        } on AuthApiException catch (error) {
          // 401은 이 토큰이 서버에 없다는 것만 알려 줍니다. 다른 기기의 비밀번호
          // 변경·만료로 폐기된 토큰도, 탈퇴로 토큰까지 지워진 계정도 같은 응답을
          // 받으므로(main.py `get_current_access_token`) 탈퇴됐다고 단정하지 않습니다.
          if (error.type == AuthApiErrorType.unauthorized) {
            return _AccountActionResult(
              sessionExpiredMessage: _earlierAttemptUnresolved
                  ? '로그인이 만료돼 탈퇴됐는지 확인하지 못했어요. '
                        '다시 로그인되면 탈퇴를 다시 해 주세요.'
                  : '로그인이 만료돼 탈퇴되지 않았어요. '
                        '다시 로그인한 뒤 탈퇴해 주세요.',
            );
          }

          if (!_rejectedBeforeDeletion(error)) {
            _earlierAttemptUnresolved = true;
          }
          rethrow;
        }
        return const _AccountActionResult();
      },
      describeFailure: _describeFailure,
      onFailure: (message) {
        if (_usesKakao) {
          _showKakaoError(message);
        } else {
          setState(() => _errorText = message);
        }
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_isBusy,
      child: AlertDialog(
        title: const Text('회원 탈퇴'),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                '계정과 서버에 저장된 분석 이력이 모두 삭제됩니다.\n'
                '이 기기의 옷장도 함께 비워지며, 되돌릴 수 없습니다.',
                style: TextStyle(height: 1.5),
              ),
              const SizedBox(height: 16),
              if (_usesKakao)
                ..._buildKakaoConfirmation(context)
              else
                _PasswordField(
                  controller: _passwordController,
                  label: '비밀번호 확인',
                  errorText: _errorText,
                  autofocus: true,
                  enabled: !isSubmitting,
                  autofillHints: const [AutofillHints.password],
                  textInputAction: TextInputAction.done,
                  onSubmitted: _submit,
                  onChanged: () {
                    if (_errorText == null) return;
                    setState(() => _errorText = null);
                  },
                ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: _isBusy ? null : () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: _isBusy
                ? null
                : _usesKakao
                ? _submitWithKakao
                : _submit,
            style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
            child: _isBusy
                ? const _SubmitProgress()
                : Text(
                    _usesKakao ? '카카오로 확인하고 탈퇴' : '탈퇴',
                    style: const TextStyle(color: Colors.white),
                  ),
          ),
        ],
      ),
    );
  }

  /// 비밀번호 칸 대신 보이는 카카오 확인 안내와, 확인이 실패했을 때의 이유입니다.
  List<Widget> _buildKakaoConfirmation(BuildContext context) {
    return [
      const Text('카카오계정으로 한 번 더 로그인하면 탈퇴돼요.', style: TextStyle(height: 1.5)),
      if (_errorText case final message?) ...[
        const SizedBox(height: 12),
        // Android 는 live region 이라 스스로 읽고, iOS 는 [announceFieldError] 로 읽습니다.
        Semantics(
          liveRegion: true,
          child: Text(
            message,
            style: TextStyle(
              color: Theme.of(context).colorScheme.error,
              height: 1.5,
            ),
          ),
        ),
      ],
    ];
  }
}

/// 되돌릴 수 없는 요청이 진행되는 동안 화면 조작을 막는 대화상자입니다.
///
/// 로그아웃처럼 대화상자 밖에서 수행되는 요청은 이걸로 덮어야 대기 중에
/// 다른 계정 작업이 시작되는 것을 막을 수 있습니다.
class _BlockingProgressDialog extends StatelessWidget {
  const _BlockingProgressDialog({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        content: Row(
          children: [
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
            const SizedBox(width: 16),
            Expanded(child: Text(message)),
          ],
        ),
      ),
    );
  }
}

/// 요청이 진행 중임을 버튼 안에서 알리는 작은 표시기입니다.
class _SubmitProgress extends StatelessWidget {
  const _SubmitProgress();

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: 18,
      height: 18,
      child: CircularProgressIndicator(
        strokeWidth: 2,
        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        semanticsLabel: '처리 중',
      ),
    );
  }
}

/// 계정 관리 대화상자들이 공유하는 비밀번호 입력 필드입니다.
///
/// 로그인·회원가입 화면과 같은 수준을 유지하도록 표시 토글과 autofill 힌트를 둡니다.
class _PasswordField extends StatefulWidget {
  const _PasswordField({
    required this.controller,
    required this.label,
    this.helperText,
    this.errorText,
    this.autofocus = false,
    this.enabled = true,
    this.autofillHints,
    this.textInputAction = TextInputAction.next,
    this.onChanged,
    this.onSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final String? helperText;
  final String? errorText;
  final bool autofocus;
  final bool enabled;
  final Iterable<String>? autofillHints;
  final TextInputAction textInputAction;
  final VoidCallback? onChanged;
  final VoidCallback? onSubmitted;

  @override
  State<_PasswordField> createState() => _PasswordFieldState();
}

class _PasswordFieldState extends State<_PasswordField> {
  bool _isObscured = true;

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);

    return TextField(
      controller: widget.controller,
      obscureText: _isObscured,
      autofocus: widget.autofocus,
      enabled: widget.enabled,
      autofillHints: widget.autofillHints,
      textInputAction: widget.textInputAction,
      style: TextStyle(color: palette.textPrimary),
      decoration: InputDecoration(
        labelText: widget.label,
        helperText: widget.helperText,
        errorText: widget.errorText,
        // 서버 메시지가 한 줄을 넘으면 잘려서 원인을 알 수 없게 되므로 접어서 보여 줍니다.
        errorMaxLines: 3,
        helperMaxLines: 2,
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
        suffixIcon: IconButton(
          onPressed: () => setState(() => _isObscured = !_isObscured),
          icon: Icon(
            _isObscured ? Icons.visibility_off : Icons.visibility,
          ),
          tooltip: _isObscured ? '비밀번호 표시' : '비밀번호 숨기기',
        ),
      ),
      onChanged: (_) => widget.onChanged?.call(),
      onSubmitted: (_) => widget.onSubmitted?.call(),
    );
  }
}
