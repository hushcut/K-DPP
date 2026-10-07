// 이메일로 받은 인증번호를 확인해 비밀번호를 새로 정하고 로그인 화면으로 돌려보내는 화면입니다.
import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'services/auth_api_service.dart';
import 'theme/app_palette.dart';
import 'utils/auth_form_validators.dart';
import 'widgets/app_back_button.dart';
import 'widgets/app_banner.dart';
import 'widgets/auth_form_widgets.dart';
import 'widgets/email_code_section.dart';
import 'widgets/number_keyboard_toolbar.dart';

/// 로그인 화면의 '비밀번호를 잊으셨나요?'에서 여는 비밀번호 찾기 화면입니다.
///
/// 경로 인자로 이메일 문자열을 받으면 이메일 칸에 채웁니다. 재설정에 성공하면 서버가 그
/// 계정의 로그인을 모두 끊고 새 토큰은 주지 않으므로, 이메일을 들고 로그인 화면으로
/// 돌아갑니다(DECISIONS 170 ⑦).
class PasswordResetScreen extends StatefulWidget {
  const PasswordResetScreen({super.key, this.authApiService, this.now});

  final AuthApiService? authApiService;

  /// 인증번호 남은 시간을 셀 시계입니다. 테스트만 바꿔 끼웁니다.
  final DateTime Function()? now;

  @override
  State<PasswordResetScreen> createState() => _PasswordResetScreenState();
}

class _PasswordResetScreenState extends State<PasswordResetScreen> {
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final GlobalKey<FormFieldState<String>> _emailFieldKey =
      GlobalKey<FormFieldState<String>>();
  final GlobalKey<EmailCodeSectionState> _codeSectionKey =
      GlobalKey<EmailCodeSectionState>();

  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _codeController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _confirmPasswordController =
      TextEditingController();
  final FocusNode _codeFocusNode = FocusNode();
  final FocusNode _passwordFocusNode = FocusNode();
  final FocusNode _confirmPasswordFocusNode = FocusNode();
  late final AuthApiService _authApiService;

  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _didLoadInitialEmail = false;

  @override
  void initState() {
    super.initState();
    _authApiService = widget.authApiService ?? AuthApiService();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    if (_didLoadInitialEmail) return;
    _didLoadInitialEmail = true;

    // 로그인 화면에 적어 둔 이메일이 있으면 한 번만 채웁니다.
    final args = ModalRoute.of(context)?.settings.arguments;
    if (args is String && args.trim().isNotEmpty) {
      _emailController.text = args.trim();
    }
  }

  @override
  void dispose() {
    _emailController.dispose();
    _codeController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    _codeFocusNode.dispose();
    _passwordFocusNode.dispose();
    _confirmPasswordFocusNode.dispose();
    super.dispose();
  }

  /// 로그인 화면에서 왔으면 pop 으로 이메일을 돌려주고, 아니면 로그인 화면으로 바꿉니다.
  void _returnToEmailLogin(String email) {
    if (Navigator.canPop(context)) {
      Navigator.pop(context, email);
      return;
    }

    Navigator.pushReplacementNamed(context, '/email-login', arguments: email);
  }

  Future<void> _handleReset() async {
    final isValid = _formKey.currentState?.validate() ?? false;
    if (!isValid) return;

    final email = _emailController.text.trim();

    setState(() {
      _isLoading = true;
    });

    try {
      await _authApiService.resetPassword(
        email: email,
        code: _codeController.text,
        newPassword: _passwordController.text,
      );

      if (!mounted) return;

      AppBanner.of(
        context,
      ).show('비밀번호를 다시 설정했어요. 새 비밀번호로 로그인해 주세요.', kind: AppBannerKind.success);

      _returnToEmailLogin(email);
    } on AuthApiException catch (error) {
      if (!mounted) return;

      final shownOnCodeField =
          _codeSectionKey.currentState?.showSubmitError(error) ?? false;
      if (shownOnCodeField) return;

      AppBanner.of(
        context,
      ).show(error.userMessage, kind: AppBannerKind.failure);
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  // iOS 숫자 키패드에는 다음 키가 없어, 번호 칸에 포커스가 있는 동안 [다음]·[완료]를 그립니다.
  Widget _buildNumberKeyboardToolbar(BuildContext context) {
    if (!NumberKeyboardToolbar.isNeeded(context)) {
      return const SizedBox.shrink();
    }

    return ListenableBuilder(
      listenable: _codeFocusNode,
      builder: (context, _) {
        if (!_codeFocusNode.hasFocus) return const SizedBox.shrink();

        return NumberKeyboardToolbar(
          onNext: _passwordFocusNode.requestFocus,
          onDone: _codeFocusNode.unfocus,
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final palette = AppPalette.of(context);
    final backgroundColor = palette.background;
    final primaryText = palette.textPrimary;
    final secondaryText = isDark
        ? const Color(0xFFD1D1D6)
        : const Color(0xFF8C8C8C);
    final iconColor = isDark
        ? const Color(0xFFB8B8BE)
        : const Color(0xFF8C8C8C);

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
          '비밀번호 찾기',
          style: TextStyle(
            color: primaryText,
            fontSize: 20,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
      body: SafeArea(
        // 본문이 키보드만큼 줄어들므로, 맨 아래에 둔 막대가 키보드 바로 위에 놓입니다.
        child: Column(
          children: [
            Expanded(
              child: Form(
                key: _formKey,
                child: LayoutBuilder(
                  builder: (context, constraints) {
                    return SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 24),
                      child: ConstrainedBox(
                        // 아래 인셋(자판 등)이 앱바 아래를 다 덮으면 maxHeight 가 0 이 되므로
                        // 빼고 남은 값이 음수가 되지 않게 0 에서 멈춥니다.
                        constraints: BoxConstraints(
                          minHeight: math.max(0.0, constraints.maxHeight - 12),
                        ),
                        child: IntrinsicHeight(
                          child: Column(
                            children: [
                              const SizedBox(height: 40),
                              Text(
                                '비밀번호를 새로 정해요',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w700,
                                  color: primaryText,
                                ),
                              ),
                              const SizedBox(height: 10),
                              Text(
                                // 한글은 글자 단위로 줄이 바뀌어 '다 / 른'처럼 끊기므로 문장마다 줄을 나눕니다.
                                '가입한 이메일로 받은 인증번호를 넣어 주세요.\n'
                                '다른 기기의 로그인도 모두 풀려요.',
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 14,
                                  color: secondaryText,
                                  height: 1.5,
                                ),
                              ),
                              const SizedBox(height: 36),
                              TextFormField(
                                key: _emailFieldKey,
                                controller: _emailController,
                                keyboardType: TextInputType.emailAddress,
                                textInputAction: TextInputAction.next,
                                autofillHints: const [
                                  AutofillHints.username,
                                  AutofillHints.email,
                                ],
                                autocorrect: false,
                                validator: validateEmailInput,
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '이메일',
                                  hintText: 'honggildong@example.com',
                                ),
                              ),
                              const SizedBox(height: 12),
                              EmailCodeSection(
                                key: _codeSectionKey,
                                purpose: EmailCodePurpose.passwordReset,
                                authApiService: _authApiService,
                                emailFieldKey: _emailFieldKey,
                                emailController: _emailController,
                                codeController: _codeController,
                                codeFocusNode: _codeFocusNode,
                                enabled: !_isLoading,
                                onCodeSubmitted: (_) =>
                                    _passwordFocusNode.requestFocus(),
                                now: widget.now ?? DateTime.now,
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _passwordController,
                                focusNode: _passwordFocusNode,
                                obscureText: _obscurePassword,
                                textInputAction: TextInputAction.next,
                                // 기본 '다음'은 칸 안의 눈 아이콘으로 가 키보드가 내려갑니다.
                                onEditingComplete:
                                    _confirmPasswordFocusNode.requestFocus,
                                autofillHints: const [
                                  AutofillHints.newPassword,
                                ],
                                enableSuggestions: false,
                                autocorrect: false,
                                validator: validateNewPassword,
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '새 비밀번호',
                                  hintText: '8자 이상 입력',
                                  suffixIcon: IconButton(
                                    onPressed: () {
                                      setState(() {
                                        _obscurePassword = !_obscurePassword;
                                      });
                                    },
                                    tooltip: _obscurePassword
                                        ? '새 비밀번호 표시'
                                        : '새 비밀번호 숨기기',
                                    icon: Icon(
                                      _obscurePassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: iconColor,
                                    ),
                                  ),
                                ),
                              ),
                              const SizedBox(height: 16),
                              TextFormField(
                                controller: _confirmPasswordController,
                                focusNode: _confirmPasswordFocusNode,
                                obscureText: _obscureConfirmPassword,
                                textInputAction: TextInputAction.done,
                                autofillHints: const [
                                  AutofillHints.newPassword,
                                ],
                                enableSuggestions: false,
                                autocorrect: false,
                                validator: (value) =>
                                    validatePasswordConfirmation(
                                      value,
                                      _passwordController.text,
                                    ),
                                style: TextStyle(color: primaryText),
                                cursorColor: AppPalette.accent,
                                decoration: authInputDecoration(
                                  context,
                                  labelText: '새 비밀번호 확인',
                                  hintText: '새 비밀번호 다시 입력',
                                  suffixIcon: IconButton(
                                    onPressed: () {
                                      setState(() {
                                        _obscureConfirmPassword =
                                            !_obscureConfirmPassword;
                                      });
                                    },
                                    tooltip: _obscureConfirmPassword
                                        ? '새 비밀번호 확인 표시'
                                        : '새 비밀번호 확인 숨기기',
                                    icon: Icon(
                                      _obscureConfirmPassword
                                          ? Icons.visibility_off_outlined
                                          : Icons.visibility_outlined,
                                      color: iconColor,
                                    ),
                                  ),
                                ),
                                onFieldSubmitted: (_) {
                                  if (!_isLoading) {
                                    _handleReset();
                                  }
                                },
                              ),
                              const SizedBox(height: 32),
                              AuthSubmitButton(
                                label: '비밀번호 다시 설정',
                                loadingSemanticsLabel: '비밀번호 재설정 처리 중',
                                isLoading: _isLoading,
                                onPressed: _handleReset,
                              ),
                              const Spacer(),
                              const SizedBox(height: 24),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
            _buildNumberKeyboardToolbar(context),
          ],
        ),
      ),
    );
  }
}
