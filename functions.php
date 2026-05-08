<?php
/**
 * Nursify Aesthetics - functions.php
 *
 * Registers and enqueues all assets, defines theme supports,
 * and outputs structured data / SEO meta tags.
 */

// ============================================
// THEME SETUP
// ============================================
add_action( 'after_setup_theme', function () {
    add_theme_support( 'title-tag' );
    add_theme_support( 'post-thumbnails' );
    add_theme_support( 'html5', [ 'search-form', 'comment-form', 'gallery', 'caption' ] );
} );

// ============================================
// ENQUEUE STYLES & SCRIPTS
// ============================================
add_action( 'wp_enqueue_scripts', function () {

    // Main stylesheet
    wp_enqueue_style(
        'nursify-styles',
        get_template_directory_uri() . '/assets/css/nursify.css',
        [],
        '1.0.0'
    );

    // Luxury concierge stylesheet (loaded on concierge pages only)
    if ( is_page( [ 'concierge-medical-spa-rio-rancho', 'concierge-medical-spa-santa-fe', 'concierge-medical-spa-corrales', 'concierge-medical-spa-albuquerque' ] ) ) {
        wp_enqueue_style(
            'nursify-luxury',
            get_template_directory_uri() . '/assets/css/luxury-concierge.css',
            [ 'nursify-styles' ],
            '1.0.0'
        );
    }

    // Main JS (deferred, loaded after DOM)
    wp_enqueue_script(
        'nursify-scripts',
        get_template_directory_uri() . '/assets/js/nursify.js',
        [],         // no dependencies
        '1.0.0',
        true        // load in footer
    );

} );

// ============================================
// STRUCTURED DATA (JSON-LD)
// ============================================
add_action( 'wp_head', function () {
    if ( ! is_front_page() ) return; // only on the landing page
    ?>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "MedicalBusiness",
        "name": "Nursify Aesthetics & Wellness",
        "url": "https://nursifyaesthetics.com",
        "telephone": "+1-505-500-7900",
        "email": "nursifyaesthetics@gmail.com",
        "image": "https://nursifyaesthetics.com/wp-content/uploads/2025/10/NursifyLogo-e1760754791381.png",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "5500 San Mateo Blvd NE",
            "addressLocality": "Albuquerque",
            "addressRegion": "NM",
            "postalCode": "87109",
            "addressCountry": "US"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": "35.1495",
            "longitude": "-106.5893"
        },
        "areaServed": ["Albuquerque", "Rio Rancho", "Santa Fe", "Los Alamos", "Corrales"],
        "priceRange": "$$",
        "medicalSpecialty": ["Aesthetic Medicine", "Cosmetic Treatments", "Wellness Therapy"],
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "5.0",
            "reviewCount": "12",
            "bestRating": "5",
            "worstRating": "1"
        }
    }
    </script>
    <?php
} );

// ============================================
// AGGREGATE RATING SCHEMA - SERVICE PAGES
// Outputs on every service page to enable star rich snippets.
// UPDATE ratingValue and reviewCount as you collect more reviews.
// ============================================
add_action( 'wp_head', function () {

    // Only run on service and concierge pages, not homepage or blog
    if ( is_front_page() ) return;

    $template = get_page_template_slug();
    if ( ! $template ) return;

    // Pages to add rating schema to
    $service_templates = [
        'page-botox-albuquerque.php'                        => 'Botox & Wrinkle Relaxers Albuquerque',
        'page-dermal-fillers-albuquerque.php'               => 'Dermal Fillers Albuquerque',
        'page-microneedling-albuquerque.php'                => 'Microneedling Albuquerque',
        'page-wellness-injections-albuquerque.php'          => 'Wellness Injections Albuquerque',
        'page-medical-weight-loss-albuquerque.php'          => 'Medical Weight Loss Albuquerque',
        'page-prf-hair-restoration-albuquerque.php'         => 'PRF Hair Restoration Albuquerque',
        'page-skincare-albuquerque.php'                     => 'Epicutis Skincare Albuquerque',
        'page-concierge-medical-spa-albuquerque.php'        => 'Concierge Medical Spa Albuquerque',
        'page-concierge-medical-spa-rio-rancho.php'         => 'Concierge Medical Spa Rio Rancho',
        'page-concierge-medical-spa-santa-fe.php'           => 'Concierge Medical Spa Santa Fe',
        'page-concierge-medical-spa-corrales.php'           => 'Concierge Medical Spa Corrales',
        'page-about-our-practice.php'                       => 'Nursify Aesthetics & Wellness',
    ];

    if ( ! isset( $service_templates[ $template ] ) ) return;

    $service_name = $service_templates[ $template ];
    $page_url     = get_permalink();

    // ── UPDATE THESE TWO VALUES AS YOU GET MORE REVIEWS ──
    $rating_value = '5.0';
    $review_count = '12';
    // ─────────────────────────────────────────────────────
    ?>
    <script type="application/ld+json">
    {
        "@context": "https://schema.org",
        "@type": "MedicalBusiness",
        "name": "Nursify Aesthetics & Wellness - <?php echo esc_js( $service_name ); ?>",
        "url": "<?php echo esc_js( $page_url ); ?>",
        "telephone": "+1-505-500-7900",
        "image": "https://nursifyaesthetics.com/wp-content/uploads/2025/10/NursifyLogo-e1760754791381.png",
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "5500 San Mateo Blvd NE",
            "addressLocality": "Albuquerque",
            "addressRegion": "NM",
            "postalCode": "87109",
            "addressCountry": "US"
        },
        "aggregateRating": {
            "@type": "AggregateRating",
            "ratingValue": "<?php echo esc_js( $rating_value ); ?>",
            "reviewCount": "<?php echo esc_js( $review_count ); ?>",
            "bestRating": "5",
            "worstRating": "1"
        }
    }
    </script>
    <?php
} );

// ============================================
// SEO META TAGS (front page only)
// ============================================
add_action( 'wp_head', function () {
    if ( ! is_front_page() ) return;
    ?>
    <meta name="description" content="Nursify Aesthetics is a medical spa serving Albuquerque, Rio Rancho, Santa Fe and Los Alamos offering Botox, fillers, microneedling, GLP-1 therapy and wellness injections.">
    <meta name="robots"      content="index, follow">
    <link  rel="canonical"   href="https://nursifyaesthetics.com/">

    <!-- Geo -->
    <meta name="geo.region"    content="US-NM">
    <meta name="geo.placename" content="Albuquerque">

    <!-- Open Graph -->
    <meta property="og:title"       content="Nursify Aesthetics Medical Spa">
    <meta property="og:description" content="Medical spa treatments including Botox, fillers, weight loss therapy and skin rejuvenation in New Mexico.">
    <meta property="og:url"         content="https://nursifyaesthetics.com/">
    <meta property="og:type"        content="website">
    <?php
} );

// ============================================
// GOOGLE TAG MANAGER
// ============================================
add_action( 'wp_head', function () {
    ?><!-- Google Tag Manager --><script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);})(window,document,'script','dataLayer','GTM-K3M5WQSR');</script><!-- End Google Tag Manager --><?php
}, 1 );

add_action( 'wp_body_open', function () {
    ?><!-- Google Tag Manager (noscript) --><noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-K3M5WQSR" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript><!-- End Google Tag Manager (noscript) --><?php
} );

// ============================================
// HIDE DEFAULT WP ADMIN BAR ON FRONT END
// (optional: remove if you need it)
// ============================================
add_filter( 'show_admin_bar', '__return_false' );

// ============================================
// DYNAMIC SERVICE PAGE - REWRITE RULES
// Captures URLs like /botox-albuquerque/ and
// routes them to the Dynamic Service Page template.
// After adding this, go to Settings > Permalinks
// and click Save Changes to flush rewrite rules.
// ============================================

// Register custom query vars
add_filter( 'query_vars', function( $vars ) {
    $vars[] = 'nursify_service';
    $vars[] = 'nursify_city_page';
    return $vars;
} );

// Add rewrite rules for all service + city combinations
add_action( 'init', function () {
    require_once get_template_directory() . '/includes/config.php';
    global $nursify_services, $nursify_cities;

    foreach ( $nursify_services as $service_slug => $service ) {
        foreach ( $nursify_cities as $city_slug => $city ) {
            $page_slug = $service_slug . '-' . $city_slug;

            // Try to get page ID for more reliable routing
            $page = get_page_by_path( $page_slug );
            $query_string = $page
                ? 'index.php?page_id=' . $page->ID . '&nursify_service=' . $service_slug . '&nursify_city_page=' . $city_slug
                : 'index.php?pagename=dynamic-service&nursify_service=' . $service_slug . '&nursify_city_page=' . $city_slug;

            $pattern = '^' . preg_quote( $service_slug, '/' ) . '-' . preg_quote( $city_slug, '/' ) . '/?$';
            add_rewrite_rule( $pattern, $query_string, 'top' );
        }
    }
} );

// Enqueue dynamic service page CSS when on a DSP page
add_action( 'wp_enqueue_scripts', function () {
    if ( get_query_var('nursify_service') ) {
        wp_enqueue_style(
            'nursify-dsp',
            get_template_directory_uri() . '/assets/css/dynamic-service-page.css',
            [ 'nursify-styles' ],
            '1.0.0'
        );
    }
}, 20 );

// ============================================
// DYNAMIC SERVICES DROPDOWN NAV
// Generates nav links for all services x cities
// from config.php. Used in header-nav.php via
// nursify_get_nav_services()
// ============================================
function nursify_get_nav_services() {
    require_once get_template_directory() . '/includes/config.php';
    global $nursify_services;
    return $nursify_services;
}

function nursify_get_nav_cities() {
    require_once get_template_directory() . '/includes/config.php';
    global $nursify_cities;
    return $nursify_cities;
}


// ============================================
// NURSIFY AI CHAT WIDGET
// Floating chat assistant powered by Claude
// ============================================
add_action( 'wp_footer', function () {
    $widget_url = esc_url( get_template_directory_uri() . '/assets/js/nursify-chat-widget.js?ver=1.0.0' );
    // Delay chat widget load by 5 seconds so it never blocks LCP or FCP
    echo '<script>setTimeout(function(){var s=document.createElement("script");s.src="' . $widget_url . '";s.async=true;document.body.appendChild(s);},5000);</script>' . "
";
} );


// ============================================
// PERFORMANCE: Non-blocking Google Fonts
// Preconnect + async load for Core Web Vitals
// ============================================
add_action( 'wp_head', function () {
    ?>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link rel="preload" as="style" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300;1,400&family=Montserrat:wght@300;400;500;600&display=swap" onload="this.onload=null;this.rel='stylesheet'">
    <noscript><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,300;0,400;1,300;1,400&family=Montserrat:wght@300;400;500;600&display=swap"></noscript>
    <?php
}, 1 );


// ============================================
// PERFORMANCE: Defer non-critical JS
// ============================================
add_filter( 'script_loader_tag', function ( $tag, $handle ) {
    $defer = [ 'nursify-scripts', 'nursify-chat-widget' ];
    if ( in_array( $handle, $defer ) ) {
        return str_replace( ' src', ' defer src', $tag );
    }
    return $tag;
}, 10, 2 );

// ============================================
// PERFORMANCE: Add fetchpriority=high to LCP image
// ============================================
add_filter( 'wp_get_attachment_image_attributes', function( $attr ) {
    return $attr;
} );

// ============================================
// PERFORMANCE: Remove query strings from static assets
// ============================================
add_filter( 'style_loader_src', 'nursify_remove_query_strings', 10 );
add_filter( 'script_loader_src', 'nursify_remove_query_strings', 10 );
function nursify_remove_query_strings( $src ) {
    if ( strpos( $src, '?ver=' ) ) {
        $src = remove_query_arg( 'ver', $src );
    }
    return $src;
}


// ============================================
// PERFORMANCE: Preload LCP hero image
// Tells browser to fetch hero image immediately
// ============================================


// ============================================
// UPLOAD PORTAL: Enqueue JS for /upload page
// ============================================
add_action( 'wp_enqueue_scripts', function() {
    if ( ! is_page( 'upload' ) ) return;

    $railway_url   = 'https://nursify-chat-backend-production.up.railway.app/upload/result';
    $upload_secret = defined('NURSIFY_UPLOAD_SECRET') ? NURSIFY_UPLOAD_SECRET : 'nursify-upload-2025';

    // Register a dummy handle to attach inline script to
    wp_register_script( 'nursify-upload', false, [], null, true );
    wp_enqueue_script( 'nursify-upload' );

    $js = "
const RAILWAY_URL   = " . json_encode($railway_url) . ";
const UPLOAD_SECRET = " . json_encode($upload_secret) . ";

document.addEventListener('DOMContentLoaded', function() {

  // Photo preview
  const photoInput = document.getElementById('photo_file');
  if (photoInput) {
    photoInput.addEventListener('change', function(e) {
      const file = e.target.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = ev => {
        document.getElementById('preview-img').src = ev.target.result;
        document.getElementById('photo-name').textContent = file.name + ' (' + (file.size / 1024).toFixed(0) + ' KB)';
        document.getElementById('photo-preview').style.display = 'block';
        document.querySelector('.drop-zone-label').textContent = 'Photo selected \u2713';
      };
      reader.readAsDataURL(file);
    });
  }

  // Upload form submit
  const uploadForm = document.getElementById('upload-form');
  if (uploadForm) {
    uploadForm.addEventListener('submit', async function(e) {
      e.preventDefault();

      const btn        = document.getElementById('submit-btn');
      const errorBox   = document.getElementById('error-box');
      const successBox = document.getElementById('success-box');
      const progress   = document.getElementById('progress-bar');
      const fill       = document.getElementById('progress-fill');

      errorBox.style.display  = 'none';
      btn.disabled             = true;
      btn.textContent          = 'Uploading\u2026';
      progress.style.display  = 'block';

      let pct = 10;
      const ticker = setInterval(() => {
        pct = Math.min(pct + 5, 85);
        fill.style.width = pct + '%';
      }, 300);

      const fd = new FormData();
      fd.append('photo',         document.getElementById('photo_file').files[0]);
      fd.append('title',         document.getElementById('photo_title').value);
      fd.append('instagram_url', document.getElementById('instagram_url').value);
      fd.append('procedure',     document.getElementById('procedure_type').value);
      fd.append('show_on_home',  document.getElementById('show_on_home').checked ? '1' : '0');
      fd.append('secret',        UPLOAD_SECRET);

      try {
        const resp = await fetch(RAILWAY_URL, { method: 'POST', body: fd });
        const data = await resp.json();

        clearInterval(ticker);
        fill.style.width = '100%';

        if (resp.ok && data.success) {
          uploadForm.style.display  = 'none';
          successBox.style.display  = 'block';
        } else {
          errorBox.textContent      = data.detail || 'Upload failed. Please try again.';
          errorBox.style.display    = 'block';
          btn.disabled              = false;
          btn.textContent           = 'Publish Photo to Website';
          progress.style.display    = 'none';
        }
      } catch (err) {
        clearInterval(ticker);
        errorBox.textContent     = 'Network error: ' + err.message;
        errorBox.style.display   = 'block';
        btn.disabled             = false;
        btn.textContent          = 'Publish Photo to Website';
        progress.style.display   = 'none';
      }
    });
  }

});
";

    wp_add_inline_script( 'nursify-upload', $js );
} );
