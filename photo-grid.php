<?php
/**
 * Template Part: Photo Grid (Homepage)
 *
 * Fetches photos from Railway API (Postgres + R2).
 * Falls back to hardcoded array if API is unavailable.
 */

$railway_api = 'https://nursify-chat-backend-production.up.railway.app/upload/photos?show_on_home=true';
$photos      = [];

// ── Fetch from Railway ────────────────────────────────────────────────
$response = wp_remote_get( $railway_api, [ 'timeout' => 5 ] );

if ( ! is_wp_error($response) && wp_remote_retrieve_response_code($response) === 200 ) {
    $body = json_decode( wp_remote_retrieve_body($response), true );
    if ( ! empty($body['photos']) ) {
        foreach ( $body['photos'] as $p ) {
            $photos[] = [
                'src' => $p['src'],
                'url' => $p['url'],
                'alt' => $p['title'],
            ];
        }
    }
}

// ── Hardcoded fallback ────────────────────────────────────────────────
if ( empty($photos) ) {
    $photos = [
        [ 'url' => 'https://www.instagram.com/p/DU_KamGjeBQ/?img_index=3', 'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Service-Menu.jpg',   'alt' => 'Nursify Aesthetics service menu' ],
        [ 'url' => 'https://www.instagram.com/p/DVYnfntDfNq/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Expo2026.jpg',         'alt' => 'Nursify at Expo 2026' ],
        [ 'url' => 'https://www.instagram.com/p/DVJNzVwjQ3N/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/MN1.jpg',              'alt' => 'Microneedling result Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DVgVPJBkbAC/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/MN2.jpg',              'alt' => 'SkinPen microneedling result' ],
        [ 'url' => 'https://www.instagram.com/p/DUa4CIdjeKs/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/CF1.jpg',              'alt' => 'Chin filler result at Nursify Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DWJ_ZMylJU_/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/FacialBalancing1.jpg', 'alt' => 'Facial Balancing Before and After' ],
        [ 'url' => 'https://www.instagram.com/p/DVRNv1NjQH2/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler8.jpg',          'alt' => 'Dermal filler result Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DVqi2tfETUi/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler7.jpg',          'alt' => 'Filler result at Nursify' ],
        [ 'url' => 'https://www.instagram.com/p/DU0rHU9jeOk/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler6.jpg',          'alt' => 'Natural-looking filler result' ],
        [ 'url' => 'https://www.instagram.com/p/DUiqCMPFArW/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Filler5.jpg',          'alt' => 'Juvederm filler result' ],
        [ 'url' => 'https://www.instagram.com/p/DRvgBoujYCN/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/LipFiller.jpg',        'alt' => 'Lip filler result Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DT-ovB4jVaF/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/LipFlip1.jpg',         'alt' => 'Lip flip with Botox' ],
        [ 'url' => 'https://www.instagram.com/p/DWEmzfFDRgH/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Botox-Albuquerque15.jpg','alt' => 'Botox result at Nursify Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DV6EWKGlBSH/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2026/03/Barbie-tox.jpg',       'alt' => 'Barbie Tox Botox result' ],
        [ 'url' => 'https://www.instagram.com/p/DRM2rI_jYpx/?img_index=1',  'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Botox1.jpg',           'alt' => 'Botox treatment at Nursify Aesthetics' ],
        [ 'url' => 'https://www.instagram.com/p/DR42HgzDawz/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Wellness-Shot.jpg',     'alt' => 'Wellness vitamin injection Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DSVCL98DQR4/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review1.jpg',           'alt' => 'Five star review Nursify Aesthetics' ],
        [ 'url' => 'https://www.instagram.com/p/DR7S2IbDdiq/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review2.jpg',           'alt' => 'Client review Nursify Albuquerque' ],
        [ 'url' => 'https://www.instagram.com/p/DRSI2p2DTL4/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review3.jpg',           'alt' => 'Happy client review Nursify' ],
        [ 'url' => 'https://www.instagram.com/p/DQ8dlCaDfDQ/',              'src' => 'https://nursifyaesthetics.com/wp-content/uploads/2025/12/Review4.jpg',           'alt' => 'Client testimonial Nursify Aesthetics' ],
    ];
}
?>

<section class="instagram-photo-grid" id="pics">
    <h2>Real Results. Real Confidence.</h2>
    <p class="insta-subtext">See real transformations from our clients</p>

    <div class="insta-grid">
        <?php foreach ( $photos as $photo ) : ?>
            <a href="<?php echo esc_url( $photo['url'] ); ?>" target="_blank" rel="noopener noreferrer">
                <img src="<?php echo esc_url( $photo['src'] ); ?>"
                     alt="<?php echo esc_attr( $photo['alt'] ); ?>"
                     loading="lazy">
            </a>
        <?php endforeach; ?>
    </div>

    <div style="text-align:center;margin-top:40px;">
        <a href="https://www.instagram.com/nursifyaestheticsllc/"
           class="btn btn-primary" target="_blank" rel="noopener noreferrer">
            Follow Us on Instagram
        </a>
        <a href="https://nursifyaesthetics.myaestheticrecord.com/online-booking"
           class="btn btn-primary" target="_blank" rel="noopener noreferrer">
            Book Consultation
        </a>
    </div>
</section>
