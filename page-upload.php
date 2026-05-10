<?php
/**
 * Template Name: Nursify Upload Portal
 * Pure HTML form — posts directly to Railway. No JS required.
 */
defined('ABSPATH') || exit;

$upload_pass  = defined('NURSIFY_UPLOAD_PASSWORD') ? NURSIFY_UPLOAD_PASSWORD : 'nursify2025';
$token        = substr(hash_hmac('sha256', $upload_pass, wp_salt('auth')), 0, 16);
$authed       = isset($_GET['t']) && $_GET['t'] === $token;
$error        = '';

if ( isset($_POST['nursify_login']) ) {
    if ( sanitize_text_field($_POST['upload_password'] ?? '') === $upload_pass ) {
        wp_redirect( add_query_arg('t', $token, get_permalink()) );
        exit;
    }
    $error = 'Incorrect password. Try again.';
}

$railway_url   = 'https://nursify-chat-backend-production.up.railway.app/upload/result';
$upload_secret = defined('NURSIFY_UPLOAD_SECRET') ? NURSIFY_UPLOAD_SECRET : 'nursify-upload-2025';
$success       = isset($_GET['uploaded']) && $_GET['uploaded'] === '1';

$procedures = [
    'botox'         => 'Botox / Wrinkle Relaxers',
    'fillers'       => 'Dermal Fillers (includes Lip Filler)',
    'microneedling' => 'Microneedling',
    'wellness'      => 'Wellness Injections',
    'weight-loss'   => 'Medical Weight Loss',
    'prf-hair'      => 'PRF Hair Restoration',
    'skincare'      => 'Skincare',
    'reviews'       => 'Client Reviews / Testimonials',
    'events'        => 'Events / Brand',
    'general'       => 'General / Brand',
];
?><!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Nursify – Upload Portal</title>
<meta name="robots" content="noindex, nofollow">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400&family=Montserrat:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --pink: #ff69b4; --pink-light: #ffb6c1;
    --text: #2a2a2a; --muted: #888; --border: #f0d9e8; --white: #fff;
    --radius: 12px; --shadow: 0 4px 24px rgba(255,105,180,0.12);
  }
  body {
    font-family: 'Montserrat', sans-serif;
    background: linear-gradient(160deg,#fff5fa 0%,#fff 60%);
    min-height: 100vh; display: flex; align-items: center;
    justify-content: center; padding: 24px 16px; color: var(--text);
  }
  .portal-wrap { width: 100%; max-width: 480px; }
  .portal-header { text-align: center; margin-bottom: 32px; }
  .portal-header h1 { font-family: 'Cormorant Garamond', serif; font-size: 28px; font-weight: 400; }
  .portal-header p { font-size: 12px; font-weight: 500; letter-spacing: 0.12em; text-transform: uppercase; color: var(--pink); margin-top: 6px; }
  .card { background: var(--white); border-radius: var(--radius); box-shadow: var(--shadow); border: 1px solid var(--border); padding: 32px 28px; }
  .field { margin-bottom: 20px; }
  .field label { display: block; font-size: 11px; font-weight: 600; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); margin-bottom: 7px; }
  .field input[type=text], .field input[type=password], .field input[type=url],
  .field input[type=file], .field select {
    width: 100%; padding: 12px 14px; font-family: 'Montserrat', sans-serif;
    font-size: 14px; border: 1.5px solid var(--border); border-radius: 8px;
    background: #fafafa; color: var(--text); -webkit-appearance: none; appearance: none;
  }
  .field input[type=file] { padding: 10px; cursor: pointer; }
  .field input:focus, .field select:focus { outline: none; border-color: var(--pink); box-shadow: 0 0 0 3px rgba(255,105,180,.12); background: var(--white); }
  .field-hint { font-size: 11px; color: var(--muted); margin-top: 5px; }
  .check-row { display: flex; align-items: center; gap: 10px; cursor: pointer; }
  .check-row input[type=checkbox] { width: 18px; height: 18px; accent-color: var(--pink); flex-shrink: 0; }
  .check-row span { font-size: 13px; line-height: 1.4; }
  .btn-upload {
    width: 100%; padding: 14px;
    background: linear-gradient(135deg, var(--pink) 0%, var(--pink-light) 100%);
    color: var(--white); border: none; border-radius: 8px;
    font-family: 'Montserrat', sans-serif; font-size: 13px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; cursor: pointer; margin-top: 8px;
  }
  .btn-upload:hover { opacity: .9; }
  .alert { padding: 12px 16px; border-radius: 8px; font-size: 13px; margin-bottom: 20px; font-weight: 500; }
  .alert-error   { background: #fff0f0; color: #c0392b; border: 1px solid #ffc9c9; }
  .alert-success { background: #f0fff4; color: #27ae60; border: 1px solid #b2f2c2; }
  .divider { border: none; border-top: 1px solid var(--border); margin: 24px 0; }
  .logout-link { text-align: center; margin-top: 20px; }
  .logout-link a { font-size: 12px; color: var(--muted); text-decoration: none; }
  .success-state { text-align: center; padding: 16px 0; }
  .success-icon { font-size: 48px; margin-bottom: 12px; }
  .success-state h2 { font-family: 'Cormorant Garamond', serif; font-size: 24px; font-weight: 400; margin-bottom: 8px; }
  .success-state p { font-size: 13px; color: var(--muted); margin-bottom: 20px; }
  .btn-another {
    display: inline-block; padding: 12px 28px; background: rgba(255,105,180,.06);
    color: var(--pink); border: 1.5px solid var(--pink-light); border-radius: 8px;
    font-family: 'Montserrat', sans-serif; font-size: 12px; font-weight: 600;
    letter-spacing: 0.08em; text-transform: uppercase; text-decoration: none;
  }
  @media (max-width:480px) { .card { padding: 24px 18px; } }
</style>
</head>
<body>
<div class="portal-wrap">

  <div class="portal-header">
    <h1>Nursify Aesthetics</h1>
    <p>Photo Upload Portal</p>
  </div>

  <div class="card">

  <?php if ( ! $authed ) : ?>
    <?php if ($error) : ?><div class="alert alert-error"><?php echo esc_html($error); ?></div><?php endif; ?>
    <form method="POST" action="<?php echo esc_url(get_permalink()); ?>">
      <div class="field">
        <label for="upload_password">Password</label>
        <input type="password" id="upload_password" name="upload_password"
               placeholder="Enter your upload password" autocomplete="current-password" required>
      </div>
      <button type="submit" name="nursify_login" class="btn-upload">Sign In</button>
    </form>

  <?php elseif ($success) : ?>
    <div class="success-state">
      <div class="success-icon">🎉</div>
      <h2>Photo Published!</h2>
      <p>Your result photo is now live on the Nursify website.</p>
      <a href="<?php echo esc_url( add_query_arg('t', $token, get_permalink()) ); ?>" class="btn-another">Upload Another</a>
    </div>

  <?php else : ?>
    <!-- POST directly to Railway — Railway redirects back on success -->
    <form method="POST"
          action="<?php echo esc_url($railway_url); ?>"
          enctype="multipart/form-data">

      <input type="hidden" name="secret"       value="<?php echo esc_attr($upload_secret); ?>">
      <input type="hidden" name="redirect_url" value="<?php echo esc_url( add_query_arg(['t' => $token, 'uploaded' => '1'], get_permalink()) ); ?>">

      <div class="field">
        <label for="photo_file">Result Photo</label>
        <input type="file" id="photo_file" name="photo"
               accept="image/jpeg,image/png,image/webp" required>
        <p class="field-hint">JPG, PNG or WEBP · max 8MB</p>
      </div>

      <div class="field">
        <label for="photo_title">Photo Title / Description</label>
        <input type="text" id="photo_title" name="title"
               placeholder="e.g. Lip filler result – natural look" required>
        <p class="field-hint">Brief description used as alt text for SEO.</p>
      </div>

      <div class="field">
        <label for="instagram_url">Instagram Post URL</label>
        <input type="url" id="instagram_url" name="instagram_url"
               placeholder="https://www.instagram.com/p/XXXXXXX/" required>
      </div>

      <div class="field">
        <label for="procedure_type">Procedure Type</label>
        <select id="procedure_type" name="procedure" required>
          <option value="">— Select a procedure —</option>
          <?php foreach ($procedures as $key => $label) : ?>
            <option value="<?php echo esc_attr($key); ?>"><?php echo esc_html($label); ?></option>
          <?php endforeach; ?>
        </select>
      </div>

      <hr class="divider">

      <div class="field">
        <label class="check-row">
          <input type="checkbox" name="show_on_home" value="1" checked>
          <span>Show on homepage photo grid</span>
        </label>
      </div>

      <button type="submit" class="btn-upload">Publish Photo to Website</button>
    </form>

  <?php endif; ?>
  </div>

  <?php if ($authed && !$success) : ?>
  <div class="logout-link"><a href="<?php echo esc_url(get_permalink()); ?>">Sign out</a></div>
  <?php endif; ?>

</div>
<?php wp_footer(); ?>
</body>
</html>
