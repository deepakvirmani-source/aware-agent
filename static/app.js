/**
 * app.js — Aware PWA Frontend (v3)
 *
 * Architecture: client-side everything.
 * - Profile stored in localStorage (never sent to server)
 * - All scoring/analysis done in JS
 * - Briefing built client-side
 * - Server is a dumb news proxy only
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────

const API = {
  news:    '/api/news',
  weather: '/api/weather',
  aqi:     '/api/aqi',
  status:  '/api/status',
};

const REFRESH_INTERVAL  = 15 * 60 * 1000; // 15 minutes
const PROFILE_KEY       = 'aware_profile_v1';
const ONBOARDING_DONE_KEY = 'aware_onboarding_done';

// ── Default profile (Faridabad→Gurugram commute) ──────────────────────────────

const DEFAULT_PROFILE = {
  name:             'User',
  city:             'Faridabad',
  neighborhood:     'Sector 16',
  work_city:        'Gurugram',
  route_primary:    'Faridabad → Badarpur Border → FG Expressway → Gurugram',
  route_alt_1:      'Faridabad → Mathura Road → South Delhi → MG Road → Gurugram',
  route_alt_2:      'Faridabad → Surajkund → Gurugram via Pali Road',
  key_junctions:    'NHPC Chowk, Badarpur Border, Sarai Khale Khan, Ashram Chowk, Sohna Road, IFFCO Chowk, Golf Course Road',
  has_children:     true,
  school_board:     'CBSE',
  exercise:         'outdoor',   // 'outdoor' | 'gym' | 'none'
  aqi_sensitive:    true,
  aqi_threshold:    200,
};

// ── Keyword scoring rules (mirrors analyzer.py config.KEYWORD_RULES) ──────────

const KEYWORD_RULES = [
  {
    keywords: ['road closure', 'closed', 'blocked', 'jam', 'congestion', 'diversion', 'traffic'],
    category: 'Traffic & Commute',
    base_score: 8,
    action_template: 'Check Google Maps before leaving. Alt route: {alt_route}. May add {extra_time} to commute.',
  },
  {
    keywords: ['strike', 'bandh', 'chakka jam', 'protest', 'agitation', 'dharna', 'rally', 'march'],
    category: 'Traffic & Commute',
    base_score: 8,
    action_template: 'Possible road blockages. Work from home if possible. Alt route: {alt_route}.',
  },
  {
    keywords: ['rain', 'heavy rain', 'flood', 'waterlogging', 'storm', 'thunderstorm', 'hail'],
    category: 'Weather & Air Quality',
    base_score: 7,
    action_template: 'Carry umbrella. Leave {extra_time} early. Avoid underpasses if waterlogging reported.',
  },
  {
    keywords: ['fog', 'dense fog', 'visibility', 'cold wave', 'freezing'],
    category: 'Weather & Air Quality',
    base_score: 7,
    action_template: 'Drive slow with fog lights. Leave 30+ mins early. Visibility may be <50m on expressway.',
  },
  {
    keywords: ['heatwave', 'heat wave', 'extreme heat', 'temperature above 45', 'hot day'],
    category: 'Weather & Air Quality',
    base_score: 6,
    action_template: 'Keep water in car. Avoid outdoor activity 12-4 PM. Check AC is working.',
  },
  {
    keywords: ['aqi', 'air quality', 'pollution', 'smog', 'hazardous', 'very poor', 'severe', 'pm2.5'],
    category: 'Weather & Air Quality',
    base_score: 6,
    action_template: 'Keep car windows closed. Avoid outdoor exercise. Use air purifier at home.',
  },
  {
    keywords: ['cbse', 'board exam', 'class 10', 'class 12', 'exam date', 'date sheet', 'cbse result'],
    category: 'Education',
    base_score: 7,
    action_template: 'Heavy traffic near schools during exam time (7-10:30 AM). Leave before 8:30 or after 10:30.',
  },
  {
    keywords: ['school closed', 'school holiday', 'school shut', 'summer vacation'],
    category: 'Education',
    base_score: 5,
    action_template: 'Kids at home today. Plan accordingly.',
  },
  {
    keywords: ['metro delay', 'metro disruption', 'metro suspended', 'metro breakdown', 'violet line', 'rapid metro'],
    category: 'Traffic & Commute',
    base_score: 5,
    action_template: 'Metro disrupted. Road traffic will be heavier. Add 20 mins buffer.',
  },
  {
    keywords: ['power cut', 'power outage', 'electricity', 'dhbvn', 'load shedding', 'blackout'],
    category: 'Safety & Utilities',
    base_score: 7,
    action_template: 'Charge phone/laptop before outage. Fill water if motor won\'t run.',
  },
  {
    keywords: ['water supply', 'water cut', 'water shortage', 'pipeline', 'tanker', 'mcf'],
    category: 'Safety & Utilities',
    base_score: 7,
    action_template: 'Store water. Fill overhead tank before disruption.',
  },
  {
    keywords: ['petrol price', 'diesel price', 'fuel price', 'petrol hike', 'fuel hike', 'cng price'],
    category: 'Government & Policy',
    base_score: 4,
    action_template: 'Fuel price changed. Fill up today if prices going up tomorrow.',
  },
  {
    keywords: ['toll', 'toll price', 'toll hike', 'fastag', 'toll plaza'],
    category: 'Government & Policy',
    base_score: 5,
    action_template: 'Toll change on your expressway route. Check FASTag balance.',
  },
  {
    keywords: ['road construction', 'road repair', 'road widening', 'flyover', 'underpass', 'under construction'],
    category: 'Traffic & Commute',
    base_score: 6,
    action_template: 'Construction on route. Expect slow traffic. Alt route: {alt_route}.',
  },
  {
    keywords: ['robbery', 'theft', 'murder', 'accident', 'mishap', 'crime', 'snatch'],
    category: 'Safety & Utilities',
    base_score: 5,
    action_template: 'Stay alert in the area. Avoid late-night travel if possible.',
  },
];

// ── Profile helpers ───────────────────────────────────────────────────────────

function loadProfile() {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    return { ...DEFAULT_PROFILE, ...JSON.parse(raw) };
  } catch (e) {
    return null;
  }
}

function saveProfile(profile) {
  localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
}

function isOnboardingDone() {
  return localStorage.getItem(ONBOARDING_DONE_KEY) === '1';
}

function markOnboardingDone() {
  localStorage.setItem(ONBOARDING_DONE_KEY, '1');
}

/**
 * Build route keywords from the user's profile.
 * These are used in scoring to determine if a news item
 * affects the user's specific route / location.
 */
function buildRouteKeywords(profile) {
  const keywords = new Set();

  // City and neighborhood
  if (profile.city)         keywords.add(profile.city.toLowerCase());
  if (profile.neighborhood) keywords.add(profile.neighborhood.toLowerCase());
  if (profile.work_city)    keywords.add(profile.work_city.toLowerCase());

  // Common aliases
  const city = (profile.city || '').toLowerCase();
  if (city === 'faridabad') {
    keywords.add('faridabad');
    keywords.add('fbd');
  }
  if (city === 'gurugram' || (profile.work_city || '').toLowerCase() === 'gurugram') {
    keywords.add('gurugram');
    keywords.add('gurgaon');
    keywords.add('cyber city');
    keywords.add('golf course road');
    keywords.add('sohna road');
    keywords.add('iffco chowk');
    keywords.add('mg road');
  }

  // Key junctions from profile
  const junctions = (profile.key_junctions || '').split(',').map(j => j.trim().toLowerCase()).filter(Boolean);
  junctions.forEach(j => keywords.add(j));

  // Parse route for road names
  const route = (profile.route_primary || '') + ' ' + (profile.route_alt_1 || '') + ' ' + (profile.route_alt_2 || '');
  route.replace(/→/g, ' ').split(/[\s,]+/).forEach(token => {
    if (token.length > 3) keywords.add(token.toLowerCase());
  });

  // Always include broad NCR keywords
  ['delhi', 'ncr', 'haryana', 'badarpur', 'mathura road', 'nh-44', 'nh44', 'expressway'].forEach(k => keywords.add(k));

  return Array.from(keywords);
}

// ── Client-side scoring engine ────────────────────────────────────────────────

function buildAction(rule, text, profile) {
  let template = rule.action_template;
  if (template.includes('{alt_route}')) {
    const altRoute = profile.route_alt_1 || 'alternate route';
    template = template.replace('{alt_route}', altRoute);
  }
  if (template.includes('{extra_time}')) {
    template = template.replace('{extra_time}', '20-30 mins');
  }
  return template;
}

function buildReason(rule, text, item, routeKeywords) {
  const cat = rule.category;
  const matchedKws    = rule.keywords.filter(kw => text.includes(kw));
  const matchedRoute  = routeKeywords.filter(rk => text.includes(rk));

  if (cat === 'Traffic & Commute') {
    const location = matchedRoute.length > 0
      ? matchedRoute[0].replace(/\b\w/g, c => c.toUpperCase())
      : 'your commute route';
    const event = matchedKws[0] || 'disruption';
    return `${event.charAt(0).toUpperCase() + event.slice(1)} reported near ${location} — may affect your commute.`;
  }
  if (cat === 'Education') {
    return 'Exam/school event — heavy traffic near schools 7-10:30 AM. Your kids\' schedule may be affected.';
  }
  if (cat === 'Weather & Air Quality') {
    const event = matchedKws[0] || 'weather change';
    return `${event.charAt(0).toUpperCase() + event.slice(1)} expected — will impact your commute and outdoor plans.`;
  }
  if (cat === 'Safety & Utilities') {
    if (matchedKws.some(k => ['power cut', 'power outage', 'electricity', 'dhbvn', 'load shedding', 'blackout'].includes(k))) {
      return 'Power disruption in your area — charge devices, water supply may also be affected.';
    }
    if (matchedKws.some(k => ['water supply', 'water cut', 'water shortage', 'pipeline', 'tanker', 'mcf'].includes(k))) {
      return 'Water supply disruption — store water before the cutoff time.';
    }
    return 'Safety or utility issue in your area.';
  }
  if (cat === 'Government & Policy') {
    if (matchedKws.some(k => ['petrol price', 'diesel price', 'fuel price', 'petrol hike', 'fuel hike', 'cng price'].includes(k))) {
      return 'Fuel price change — affects your daily commute cost.';
    }
    if (matchedKws.some(k => ['toll', 'toll price', 'toll hike', 'fastag', 'toll plaza'].includes(k))) {
      return 'Toll change on your expressway route — check FASTag balance.';
    }
    return 'Policy change that may affect your daily life.';
  }
  return 'News relevant to your area — stay informed.';
}

function scoreItem(item, profile, routeKeywords) {
  const text = ((item.title || '') + ' ' + (item.summary || '')).toLowerCase();

  let bestScore   = 0;
  let bestRule    = null;
  let affectsCommute = false;
  let affectsFamily  = false;
  let matchedCategory = item.category || 'Local News';

  for (const rule of KEYWORD_RULES) {
    const kwMatch = rule.keywords.some(kw => text.includes(kw));
    if (!kwMatch) continue;

    // Weather: require 2+ keyword hits or explicit weather terms to avoid false positives
    if (rule.category === 'Weather & Air Quality') {
      const weatherHits = rule.keywords.filter(kw => text.includes(kw)).length;
      const hasExplicit = ['weather alert', 'weather warning', 'imd', 'meteorolog',
        'forecast', 'aqi', 'air quality', 'temperature'].some(w => text.includes(w));
      if (weatherHits < 2 && !hasExplicit) continue;
    }

    // Route keywords: if the rule has no route restriction, always matches
    // Education rules have no route restriction either
    let routeMatch = true;
    if (rule.category !== 'Education' && rule.category !== 'Government & Policy') {
      routeMatch = routeKeywords.some(rk => text.includes(rk));
    }

    const score = routeMatch ? rule.base_score : Math.max(rule.base_score - 3, 1);

    if (score > bestScore) {
      bestScore      = score;
      bestRule       = rule;
      matchedCategory = rule.category;

      if (rule.category === 'Traffic & Commute' || rule.keywords.some(k => ['strike', 'bandh', 'protest'].includes(k))) {
        affectsCommute = true;
      }
      if (rule.category === 'Education' && profile.has_children) {
        affectsFamily = true;
      }
    }
  }

  if (bestScore === 0) {
    return {
      ...item,
      impact_score:   2,
      severity:       'info',
      impact_reason:  'General news — not directly affecting your routine.',
      action:         '',
      affects_commute: false,
      affects_family:  false,
    };
  }

  const reason   = buildReason(bestRule, text, item, routeKeywords);
  const action   = buildAction(bestRule, text, profile);
  const severity = bestScore >= 8 ? 'high' : bestScore >= 5 ? 'medium' : 'low';

  return {
    ...item,
    category:        matchedCategory,
    impact_score:    bestScore,
    severity,
    impact_reason:   reason,
    action,
    affects_commute: affectsCommute,
    affects_family:  affectsFamily,
  };
}

function scoreAllItems(newsItems, profile) {
  const routeKeywords = buildRouteKeywords(profile);
  const scored = newsItems.map(item => scoreItem(item, profile, routeKeywords));
  scored.sort((a, b) => (b.impact_score || 0) - (a.impact_score || 0));
  return scored;
}

// ── Client-side briefing builder ──────────────────────────────────────────────

function buildBriefing(scoredItems, weather, aqi, profile) {
  const bullets = [];
  const todos   = [];

  // High-impact items
  const highItems = scoredItems.filter(i => (i.impact_score || 0) >= 7);
  for (const item of highItems.slice(0, 3)) {
    bullets.push(item.impact_reason);
    if (item.action) todos.push(item.action);
  }

  // Medium commute items
  const commuteItems = scoredItems.filter(i => i.affects_commute && (i.impact_score || 0) >= 5);
  for (const item of commuteItems.slice(0, 2)) {
    if (!highItems.includes(item)) {
      todos.push(item.action || 'Check route before leaving.');
    }
  }

  // Weather
  if (weather && weather.available) {
    const temp = weather.temp_c;
    const desc = weather.description || '';
    bullets.push(`Weather: ${temp}°C, ${desc}`);
    if (weather.alerts && weather.alerts.length > 0) {
      bullets.push(`Weather Alert: ${weather.alerts[0]}`);
      todos.push('Check weather before leaving. Carry umbrella if rain.');
    }
    if (temp > 42) {
      todos.push('Extreme heat — keep water in car, avoid 12-4 PM outdoors.');
    }
    if (temp < 5) {
      todos.push('Very cold — warm clothes, check for fog on expressway.');
    }
  }

  // AQI
  if (aqi && aqi.available) {
    const aqiVal = aqi.aqi;
    bullets.push(`AQI: ${aqiVal} (${aqi.level})`);
    const threshold = profile.aqi_sensitive ? (profile.aqi_threshold || 200) : 300;
    if (aqiVal > threshold) {
      const action = profile.exercise === 'outdoor'
        ? 'AQI above threshold — keep car windows closed. Skip outdoor exercise today. Use air purifier.'
        : 'AQI above threshold — keep car windows closed. Use air purifier at home.';
      todos.push(action);
    } else if (aqiVal > 100 && profile.has_children) {
      todos.push('AQI moderate — limit outdoor time for kids.');
    }
  }

  // Day-of-week awareness
  const now     = new Date();
  const weekday = now.toLocaleDateString('en-US', { weekday: 'long', timeZone: 'Asia/Kolkata' });
  if (weekday === 'Friday') {
    bullets.push('Friday — expect heavier evening traffic on expressway.');
    todos.push('Leave office by 6:30 PM to beat Friday rush.');
  } else if (weekday === 'Monday') {
    bullets.push('Monday — morning traffic typically 15% heavier.');
  }

  // Location-aware insights
  const loc = getCurrentLocation();
  const insights = getCommuteInsights();
  if (loc && loc.zone === 'office') {
    const hour = parseInt(now.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }));
    if (hour >= 18) {
      const eveningTraffic = scoredItems.filter(i => i.affects_commute && i.impact_score >= 5);
      if (eveningTraffic.length > 0) {
        todos.push('You\'re at office and commute disruptions reported — check route before leaving.');
      }
    }
  } else if (loc && loc.zone === 'home') {
    const hour = parseInt(now.toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }));
    if (hour >= 7 && hour <= 10) {
      const morningTraffic = scoredItems.filter(i => i.affects_commute && i.impact_score >= 7);
      if (morningTraffic.length > 0) {
        todos.unshift(`Traffic alert on your route — leave earlier than usual.`);
      }
    }
  } else if (loc && loc.zone === 'commute') {
    bullets.unshift(`You're on your commute near ${loc.zone_name}.`);
    const routeAlerts = scoredItems.filter(i => i.affects_commute && i.impact_score >= 6);
    if (routeAlerts.length > 0) {
      todos.unshift('Active disruption ahead — check Maps for live route.');
    }
  }

  // Departure pattern insight
  if (insights && insights.avgDepartHour && loc && loc.zone === 'home') {
    const avgH = Math.floor(insights.avgDepartHour);
    const avgM = Math.round((insights.avgDepartHour - avgH) * 60);
    bullets.push(`Your usual departure: ${avgH}:${String(avgM).padStart(2, '0')} AM (based on ${insights.totalTracked} data points).`);
  }

  if (bullets.length === 0) {
    bullets.push(`All clear — no major disruptions for your ${profile.city || 'local'}→${profile.work_city || 'work'} commute today.`);
  }
  if (todos.length === 0) {
    todos.push('No special actions needed. Have a smooth day!');
  }

  const maxScore = Math.max(...scoredItems.map(i => i.impact_score || 0), 0);
  const tone     = maxScore >= 8 ? 'alert' : maxScore >= 5 ? 'caution' : 'normal';

  return {
    bullets: bullets.slice(0, 5),
    todos:   todos.slice(0, 5),
    tone,
    built_at: new Date().toISOString(),
  };
}

// ── Location Tracking ────────────────────────────────────────────────────────

const LOCATION_KEY      = 'aware_location_v1';
const LOCATION_HISTORY  = 'aware_location_history_v1';
const LOCATION_INTERVAL = 5 * 60 * 1000; // 5 minutes

// Known zones — reverse geocode locally (no API needed)
const KNOWN_ZONES = [
  { name: 'Home (Faridabad)',   lat: 28.4089, lng: 77.3178, radius: 3,  zone: 'home' },
  { name: 'Gurugram (Cyber City)', lat: 28.4945, lng: 77.0887, radius: 4,  zone: 'office' },
  { name: 'Badarpur Border',    lat: 28.5063, lng: 77.3025, radius: 1.5, zone: 'commute' },
  { name: 'Ashram Chowk',       lat: 28.5700, lng: 77.2400, radius: 1,   zone: 'commute' },
  { name: 'Sohna Road',         lat: 28.4200, lng: 77.0500, radius: 2,   zone: 'commute' },
  { name: 'IFFCO Chowk',        lat: 28.4722, lng: 77.0724, radius: 1.5, zone: 'commute' },
  { name: 'South Delhi',        lat: 28.5300, lng: 77.2200, radius: 4,   zone: 'transit' },
  { name: 'Noida',              lat: 28.5355, lng: 77.3910, radius: 5,   zone: 'nearby' },
];

function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLng = (lng2 - lng1) * Math.PI / 180;
  const a = Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180) * Math.cos(lat2*Math.PI/180) * Math.sin(dLng/2)**2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
}

function detectZone(lat, lng) {
  for (const zone of KNOWN_ZONES) {
    if (haversineKm(lat, lng, zone.lat, zone.lng) <= zone.radius) {
      return zone;
    }
  }
  return { name: 'Unknown', zone: 'unknown' };
}

function getCurrentLocation() {
  return JSON.parse(localStorage.getItem(LOCATION_KEY) || 'null');
}

function getLocationHistory() {
  return JSON.parse(localStorage.getItem(LOCATION_HISTORY) || '[]');
}

function saveLocation(position) {
  const lat = position.coords.latitude;
  const lng = position.coords.longitude;
  const accuracy = position.coords.accuracy;
  const zone = detectZone(lat, lng);
  const timestamp = new Date().toISOString();

  const loc = { lat, lng, accuracy, zone: zone.zone, zone_name: zone.name, timestamp };
  localStorage.setItem(LOCATION_KEY, JSON.stringify(loc));

  // Append to history (keep last 100 entries)
  const history = getLocationHistory();
  history.push(loc);
  if (history.length > 100) history.splice(0, history.length - 100);
  localStorage.setItem(LOCATION_HISTORY, JSON.stringify(history));

  return loc;
}

function getCommuteInsights() {
  const history = getLocationHistory();
  if (history.length < 5) return null;

  const today = new Date().toISOString().slice(0, 10);
  const todayEntries = history.filter(h => h.timestamp.startsWith(today));

  // Detect if user left home today
  const leftHome = todayEntries.findIndex(h => h.zone !== 'home' && todayEntries[0]?.zone === 'home');
  let departureTime = null;
  if (leftHome > 0) {
    departureTime = todayEntries[leftHome].timestamp;
  }

  // Average departure time from history (last 7 work days)
  const departures = [];
  const weekdays = history.filter(h => {
    const d = new Date(h.timestamp);
    return d.getDay() >= 1 && d.getDay() <= 5; // Mon-Fri
  });

  let prevZone = null;
  for (const h of weekdays) {
    if (prevZone === 'home' && h.zone !== 'home') {
      departures.push(new Date(h.timestamp));
    }
    prevZone = h.zone;
  }

  const avgDepartHour = departures.length > 0
    ? departures.reduce((sum, d) => sum + d.getHours() + d.getMinutes()/60, 0) / departures.length
    : null;

  // Current zone
  const current = getCurrentLocation();

  return {
    currentZone: current?.zone || 'unknown',
    currentZoneName: current?.zone_name || 'Unknown',
    leftHomeToday: leftHome > 0,
    departureTime,
    avgDepartHour,
    totalTracked: history.length,
  };
}

function startLocationTracking() {
  if (!navigator.geolocation) {
    console.warn('[Location] Geolocation not supported');
    return;
  }

  // Request immediately
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const loc = saveLocation(pos);
      console.log(`[Location] ${loc.zone_name} (${loc.lat.toFixed(4)}, ${loc.lng.toFixed(4)})`);
      updateLocationUI(loc);
    },
    (err) => console.warn('[Location] Permission denied or error:', err.message),
    { enableHighAccuracy: false, timeout: 10000 }
  );

  // Track every 5 minutes
  setInterval(() => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const loc = saveLocation(pos);
        updateLocationUI(loc);
        // Re-score if zone changed
        const prev = getCurrentLocation();
        if (prev && prev.zone !== loc.zone) {
          console.log(`[Location] Zone changed: ${prev.zone_name} → ${loc.zone_name}`);
          if (state.allItems.length > 0 && state.profile) {
            const scored = scoreAllItems(state.allItems.map(stripScores), state.profile);
            state.allItems = scored;
            const briefing = buildBriefing(scored, state.weather, state.aqi, state.profile);
            state.briefing = briefing;
            renderBriefing(briefing);
            renderNewsCards(filterItems(state.activeTab));
          }
        }
      },
      () => {},
      { enableHighAccuracy: false, timeout: 10000 }
    );
  }, LOCATION_INTERVAL);
}

function stripScores(item) {
  return { title: item.title, summary: item.summary, source: item.source, url: item.url, timestamp: item.timestamp, category: item.category };
}

function updateLocationUI(loc) {
  const el = document.getElementById('location-indicator');
  if (!el) return;
  const icons = { home: '🏠', office: '🏢', commute: '🚗', transit: '🚌', nearby: '📍', unknown: '📍' };
  el.innerHTML = `${icons[loc.zone] || '📍'} ${loc.zone_name}`;
  el.style.display = 'inline-block';
}

// ── State ─────────────────────────────────────────────────────────────────────

const state = {
  allItems:    [],
  briefing:    null,
  weather:     null,
  aqi:         null,
  profile:     null,
  activeTab:   'all',
  activePage:  'home',
  loading:     true,
  offline:     false,
  lastUpdated: null,
  refreshTimer: null,
};

// ── DOM refs ──────────────────────────────────────────────────────────────────

const $  = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
  greeting:        $('#greeting-text'),
  lastUpdated:     $('#last-updated'),
  headerTime:      $('#header-time'),
  headerSubtitle:  $('#header-subtitle'),
  alertBanner:     $('#alert-banner'),
  alertBannerText: $('#alert-banner-text'),
  offlineBanner:   $('#offline-banner'),
  briefingBody:    $('#briefing-body'),
  briefingTone:    $('#briefing-tone-badge'),
  briefingMode:    $('#briefing-mode-label'),
  weatherCard:     $('#weather-card'),
  weatherTemp:     $('#weather-temp'),
  weatherDesc:     $('#weather-desc'),
  weatherMeta:     $('#weather-meta'),
  aqiCard:         $('#aqi-card'),
  aqiValue:        $('#aqi-value'),
  aqiLevel:        $('#aqi-level'),
  aqiMeta:         $('#aqi-meta'),
  newsContainer:   $('#news-container'),
  noResults:       $('#no-results'),
  newsCountLabel:  $('#news-count-label'),
  ptrIndicator:    $('#ptr-indicator'),
  alertsBadge:     $('#alerts-badge'),
  settingsPanel:   $('#settings-panel'),
  settingsOverlay: $('#settings-overlay'),
  onboardingScreen:$('#onboarding-screen'),
  aqiLabel:        $('#aqi-header-label'),
};

// ── Service worker ────────────────────────────────────────────────────────────

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then(reg => {
        console.log('[SW] Registered:', reg.scope);
        navigator.serviceWorker.addEventListener('message', (e) => {
          if (e.data?.type === 'NEWS_REFRESHED') loadAllData();
        });
      })
      .catch(err => console.warn('[SW] Registration failed:', err));
  });
}

// ── Utilities ─────────────────────────────────────────────────────────────────

function timeAgo(isoString) {
  if (!isoString) return '';
  const date = new Date(isoString);
  if (isNaN(date)) return '';
  const diffMs   = Date.now() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1)  return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const hours = Math.floor(diffMins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  return `${days}d ago`;
}

function greetingText(name) {
  const h = parseInt(new Date().toLocaleString('en-US', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }));
  let salutation = 'Good evening';
  if (h >= 5 && h < 12) salutation = 'Good morning';
  else if (h >= 12 && h < 17) salutation = 'Good afternoon';
  return `${salutation}, ${name || 'there'}`;
}

function scoreClass(score) {
  if (score >= 8) return 'score-high';
  if (score >= 5) return 'score-medium';
  return 'score-low';
}

function escHtml(str) {
  if (!str) return '';
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function apiFetch(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.offline = false;
    dom.offlineBanner?.classList.add('hidden');
    return data;
  } catch (err) {
    state.offline = true;
    dom.offlineBanner?.classList.remove('hidden');
    console.warn('[API] Failed:', url, err.message);
    return null;
  }
}

// ── Main data load ────────────────────────────────────────────────────────────

async function loadAllData() {
  state.loading = true;

  // Fetch all data in parallel — server returns raw news only
  const [newsData, weatherData, aqiData] = await Promise.all([
    apiFetch(API.news + '?limit=150'),
    apiFetch(API.weather),
    apiFetch(API.aqi),
  ]);

  const profile = state.profile || loadProfile() || DEFAULT_PROFILE;
  state.profile = profile;

  if (weatherData) {
    state.weather = weatherData;
    renderWeather(weatherData);
  }

  if (aqiData) {
    state.aqi = aqiData;
    renderAQI(aqiData);
  }

  if (newsData?.items) {
    // Score everything client-side
    const scored = scoreAllItems(newsData.items, profile);
    state.allItems   = scored;
    state.lastUpdated = newsData.fetched_at;

    // Build briefing client-side
    const briefing = buildBriefing(scored, weatherData, aqiData, profile);
    state.briefing = briefing;
    renderBriefing(briefing);

    renderNewsCards(filterItems(state.activeTab));
    updateAlertsBadge();
  }

  updateGreeting();
  updateLastUpdated();
  updateHeaderSubtitle();
  state.loading = false;

  if (state.refreshTimer) clearTimeout(state.refreshTimer);
  state.refreshTimer = setTimeout(loadAllData, REFRESH_INTERVAL);
}

// ── Render functions ──────────────────────────────────────────────────────────

function updateGreeting() {
  const name = state.profile?.name;
  if (dom.greeting) dom.greeting.textContent = greetingText(name);
}

function updateLastUpdated() {
  if (!dom.lastUpdated) return;
  if (state.lastUpdated) {
    dom.lastUpdated.textContent = `Updated ${timeAgo(state.lastUpdated)}`;
  }
}

function updateHeaderSubtitle() {
  if (!dom.headerSubtitle) return;
  const p = state.profile;
  if (p && p.city && p.work_city) {
    dom.headerSubtitle.textContent = `${p.city} → ${p.work_city}`;
  } else if (p && p.city) {
    dom.headerSubtitle.textContent = p.city;
  } else {
    dom.headerSubtitle.textContent = 'Delhi NCR';
  }
}

function renderBriefing(data) {
  if (!dom.briefingBody) return;

  const tone    = data.tone || 'normal';
  const bullets = data.bullets || [];

  if (dom.briefingTone) {
    const labels = { alert: 'Alert Day', caution: 'Heads Up', normal: 'All Clear' };
    dom.briefingTone.textContent = labels[tone] || 'Today';
    dom.briefingTone.className   = 'briefing-tone-badge ' + tone;
  }

  if (dom.briefingMode) {
    dom.briefingMode.textContent = 'Client-side analysis';
  }

  // Alert banner
  const highItems = state.allItems.filter(i => i.severity === 'high');
  if (highItems.length > 0 && dom.alertBanner) {
    dom.alertBanner.classList.remove('hidden');
    if (dom.alertBannerText) {
      dom.alertBannerText.textContent =
        `${highItems.length} high-priority alert${highItems.length > 1 ? 's' : ''} — action required`;
    }
  } else if (dom.alertBanner) {
    dom.alertBanner.classList.add('hidden');
  }

  if (bullets.length === 0) {
    dom.briefingBody.innerHTML = '<div class="briefing-bullet"><span class="briefing-dot">•</span><span>No major alerts today for your area. Have a smooth day!</span></div>';
    return;
  }

  let html = bullets.map(b =>
    `<div class="briefing-bullet card-enter">
      <span class="briefing-dot">•</span>
      <span>${escHtml(b)}</span>
    </div>`
  ).join('');

  const todos = data.todos || [];
  if (todos.length > 0) {
    html += `<div style="margin-top:14px; padding-top:12px; border-top:1px solid rgba(255,255,255,0.15);">
      <div style="font-size:0.7rem; text-transform:uppercase; letter-spacing:0.08em; opacity:0.7; margin-bottom:8px;">What you should do</div>`;
    html += todos.map(t =>
      `<div class="briefing-bullet card-enter" style="align-items:flex-start;">
        <span style="color:#FFD700; margin-right:6px;">→</span>
        <span style="font-weight:500;">${escHtml(t)}</span>
      </div>`
    ).join('');
    html += '</div>';
  }

  dom.briefingBody.innerHTML = html;
}

function renderWeather(data) {
  if (!data?.available) {
    if (dom.weatherTemp) dom.weatherTemp.innerHTML = '<span style="font-size:1rem;opacity:0.7">N/A</span>';
    if (dom.weatherDesc) dom.weatherDesc.textContent = 'Add OPENWEATHER_API_KEY';
    return;
  }
  if (dom.weatherTemp) dom.weatherTemp.textContent = `${data.temp_c}°C`;
  if (dom.weatherDesc) dom.weatherDesc.textContent = data.description || '';
  const parts = [];
  if (data.humidity_pct != null) parts.push(`${data.humidity_pct}% humidity`);
  if (data.wind_speed_kmh != null) parts.push(`${data.wind_speed_kmh} km/h wind`);
  if (dom.weatherMeta) dom.weatherMeta.textContent = parts.join(' · ');
}

function renderAQI(data) {
  const profile = state.profile || DEFAULT_PROFILE;
  const city = profile.city || 'Faridabad';

  // Update the AQI card label to show user's city
  const aqiLabel = dom.aqiCard?.querySelector('.env-label');
  if (aqiLabel) aqiLabel.textContent = `AQI · ${city}`;

  if (!data?.available) {
    if (dom.aqiValue) dom.aqiValue.innerHTML = '<span style="font-size:1rem;opacity:0.7">N/A</span>';
    if (dom.aqiLevel) dom.aqiLevel.textContent = 'AQI unavailable';
    return;
  }

  if (dom.aqiValue) dom.aqiValue.textContent = data.aqi;
  if (dom.aqiLevel) dom.aqiLevel.textContent = data.level || '';
  if (dom.aqiMeta)  dom.aqiMeta.textContent  = `PM2.5: ${data.pm25 ?? '—'} · PM10: ${data.pm10 ?? '—'}`;

  const card = dom.aqiCard;
  if (!card) return;
  card.className = 'env-card aqi-card';
  const level = (data.level || '').toLowerCase();
  if (level.includes('moderate'))                       card.classList.add('aqi-moderate');
  else if (level.includes('poor') && !level.includes('very')) card.classList.add('aqi-poor');
  else if (level.includes('very poor'))                  card.classList.add('aqi-very-poor');
  else if (level.includes('severe') || level.includes('hazardous')) card.classList.add('aqi-severe');
}

function filterItems(tab) {
  if (!tab || tab === 'all') return state.allItems;
  return state.allItems.filter(item => item.category === tab);
}

function renderNewsCards(items) {
  if (!dom.newsContainer) return;

  const visible = items.filter(i => (i.impact_score || 0) >= 2);

  if (dom.newsCountLabel) {
    dom.newsCountLabel.textContent =
      visible.length > 0 ? `${visible.length} item${visible.length !== 1 ? 's' : ''}` : '';
  }

  if (visible.length === 0) {
    dom.newsContainer.innerHTML = '';
    if (dom.noResults) dom.noResults.classList.remove('hidden');
    return;
  }

  if (dom.noResults) dom.noResults.classList.add('hidden');

  dom.newsContainer.innerHTML = visible.map((item, idx) => buildCardHTML(item, idx)).join('');

  dom.newsContainer.querySelectorAll('.card-expand-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const card    = btn.closest('.news-card');
      const summary = card?.querySelector('.card-summary');
      if (!summary) return;
      const expanded = summary.style.display !== 'none' && summary.style.display !== '';
      summary.style.display = expanded ? 'none' : 'block';
      btn.textContent = expanded ? 'More' : 'Less';
    });
  });

  dom.newsContainer.querySelectorAll('.news-card').forEach(card => {
    card.addEventListener('click', () => {
      const link = card.querySelector('.card-read-more');
      if (link) link.click();
    });
  });
}

function buildCardHTML(item, idx) {
  const severity = item.severity || 'info';
  const score    = item.impact_score || 0;
  const category = item.category || '';
  const title    = escHtml(item.title || '');
  const reason   = escHtml(item.impact_reason || '');
  const action   = escHtml(item.action || '');
  const summary  = escHtml((item.summary || '').substring(0, 300));
  const source   = escHtml(item.source || '');
  const url      = item.url || '#';
  const timeStr  = timeAgo(item.timestamp);
  const sBadgeClass = scoreClass(score);

  const commute = item.affects_commute
    ? `<span class="card-tag tag-commute">Commute</span>` : '';
  const family = item.affects_family
    ? `<span class="card-tag tag-family">School</span>` : '';

  const actionHtml = action
    ? `<div class="card-action">${action}</div>` : '';

  const summaryHtml = summary
    ? `<div class="card-summary" style="display:none">
        ${summary}
        ${url !== '#' ? `<a class="card-read-more" href="${url}" target="_blank" rel="noopener">Read full article →</a>` : ''}
       </div>` : '';

  const expandBtn = summary
    ? `<button class="card-expand-btn" aria-label="Toggle details">More</button>` : '';

  return `
<div class="news-card ${severity} card-enter" style="animation-delay: ${Math.min(idx * 0.04, 0.4)}s">
  <div class="card-top">
    <span class="severity-dot ${severity}"></span>
    <span class="card-category">${category}</span>
    ${commute}${family}
    <span class="impact-badge ${sBadgeClass}">${score}</span>
  </div>
  <div class="card-title">${title}</div>
  ${reason ? `<div class="card-reason">${reason}</div>` : ''}
  ${actionHtml}
  <div class="card-footer">
    ${source ? `<span class="card-meta">${source}</span>` : ''}
    ${timeStr ? `<span class="card-meta">· ${timeStr}</span>` : ''}
    ${expandBtn}
  </div>
  ${summaryHtml}
</div>`;
}

function updateAlertsBadge() {
  const highCount = state.allItems.filter(i => i.severity === 'high').length;
  if (!dom.alertsBadge) return;
  if (highCount > 0) {
    dom.alertsBadge.textContent = highCount > 9 ? '9+' : String(highCount);
    dom.alertsBadge.classList.remove('hidden');
  } else {
    dom.alertsBadge.classList.add('hidden');
  }
}

// ── Onboarding ────────────────────────────────────────────────────────────────

function showOnboarding() {
  const screen = dom.onboardingScreen;
  if (!screen) return;
  screen.classList.remove('hidden');
  // Populate defaults in onboarding form
  setVal('#ob-name',       DEFAULT_PROFILE.name !== 'User' ? DEFAULT_PROFILE.name : '');
  setVal('#ob-city',       DEFAULT_PROFILE.city);
  setVal('#ob-work-city',  DEFAULT_PROFILE.work_city);
  setVal('#ob-junctions',  DEFAULT_PROFILE.key_junctions);
  const childrenEl = $('#ob-has-children');
  if (childrenEl) childrenEl.checked = DEFAULT_PROFILE.has_children;

  // Toggle school board visibility
  toggleEl('#ob-school-board-group', DEFAULT_PROFILE.has_children);
}

function hideOnboarding() {
  const screen = dom.onboardingScreen;
  if (!screen) return;
  screen.classList.add('hidden');
}

function submitOnboarding() {
  const name      = ($('#ob-name')?.value  || '').trim() || 'there';
  const city      = ($('#ob-city')?.value  || '').trim() || DEFAULT_PROFILE.city;
  const workCity  = ($('#ob-work-city')?.value || '').trim() || DEFAULT_PROFILE.work_city;
  const junctions = ($('#ob-junctions')?.value || '').trim() || DEFAULT_PROFILE.key_junctions;
  const hasKids   = !!$('#ob-has-children')?.checked;
  const schoolBoard = hasKids ? (($('#ob-school-board')?.value || '').trim() || 'CBSE') : '';

  const profile = {
    ...DEFAULT_PROFILE,
    name,
    city,
    work_city:     workCity,
    key_junctions: junctions,
    has_children:  hasKids,
    school_board:  schoolBoard,
  };

  saveProfile(profile);
  markOnboardingDone();
  state.profile = profile;
  hideOnboarding();
  updateGreeting();
  updateHeaderSubtitle();
  loadAllData();
}

// ── Settings panel ────────────────────────────────────────────────────────────

function openSettings() {
  // Populate from current profile
  const p = state.profile || DEFAULT_PROFILE;
  setVal('#s-name',        p.name);
  setVal('#s-city',        p.city);
  setVal('#s-neighborhood',p.neighborhood);
  setVal('#s-work-city',   p.work_city);
  setVal('#s-route',       p.route_primary);
  setVal('#s-junctions',   p.key_junctions);
  setVal('#s-school-board',p.school_board);
  setVal('#s-aqi-threshold', p.aqi_threshold || 200);
  const childrenEl = $('#s-has-children');
  if (childrenEl) childrenEl.checked = !!p.has_children;
  toggleEl('#s-school-board-group', !!p.has_children);
  const aqiSensEl = $('#s-aqi-sensitive');
  if (aqiSensEl) aqiSensEl.checked = !!p.aqi_sensitive;
  const exerciseEl = $('#s-exercise');
  if (exerciseEl) exerciseEl.value = p.exercise || 'outdoor';

  dom.settingsPanel?.classList.remove('hidden');
  setTimeout(() => {
    dom.settingsPanel?.classList.add('open');
    dom.settingsOverlay?.classList.remove('hidden');
    dom.settingsOverlay?.style.setProperty('opacity', '1');
  }, 10);
}

function closeSettings() {
  dom.settingsPanel?.classList.remove('open');
  dom.settingsOverlay?.style.setProperty('opacity', '0');
  setTimeout(() => {
    dom.settingsPanel?.classList.add('hidden');
    dom.settingsOverlay?.classList.add('hidden');
  }, 350);
  $$('.nav-item').forEach(n => n.classList.remove('active'));
  $('.nav-item[data-page="home"]')?.classList.add('active');
  state.activePage = 'home';
}

function saveSettings() {
  const hasKids     = !!$('#s-has-children')?.checked;
  const aqiSensitive = !!$('#s-aqi-sensitive')?.checked;

  const profile = {
    ...(state.profile || DEFAULT_PROFILE),
    name:          ($('#s-name')?.value        || '').trim() || 'there',
    city:          ($('#s-city')?.value        || '').trim() || DEFAULT_PROFILE.city,
    neighborhood:  ($('#s-neighborhood')?.value || '').trim(),
    work_city:     ($('#s-work-city')?.value   || '').trim() || DEFAULT_PROFILE.work_city,
    route_primary: ($('#s-route')?.value       || '').trim() || DEFAULT_PROFILE.route_primary,
    key_junctions: ($('#s-junctions')?.value   || '').trim(),
    has_children:  hasKids,
    school_board:  hasKids ? (($('#s-school-board')?.value || '').trim() || 'CBSE') : '',
    aqi_sensitive: aqiSensitive,
    aqi_threshold: parseInt($('#s-aqi-threshold')?.value || '200', 10),
    exercise:      $('#s-exercise')?.value || 'outdoor',
  };

  saveProfile(profile);
  state.profile = profile;
  updateGreeting();
  updateHeaderSubtitle();
  showToast('Profile saved — your data stays on this device');
  closeSettings();

  // Re-score everything with new profile
  if (state.allItems.length > 0) {
    // Re-score the raw items (remove previous scores first)
    const rawItems = state.allItems.map(i => ({
      title:     i.title,
      summary:   i.summary,
      source:    i.source,
      url:       i.url,
      timestamp: i.timestamp,
      category:  i.category,
    }));
    const scored   = scoreAllItems(rawItems, profile);
    state.allItems = scored;
    const briefing = buildBriefing(scored, state.weather, state.aqi, profile);
    state.briefing = briefing;
    renderBriefing(briefing);
    renderNewsCards(filterItems(state.activeTab));
    updateAlertsBadge();
  }
}

// ── Tab handling ──────────────────────────────────────────────────────────────

function initTabs() {
  const tabEls = $$('#category-tabs .tab');
  tabEls.forEach(tab => {
    tab.addEventListener('click', () => {
      tabEls.forEach(t => {
        t.classList.remove('active');
        t.setAttribute('aria-selected', 'false');
      });
      tab.classList.add('active');
      tab.setAttribute('aria-selected', 'true');
      state.activeTab = tab.dataset.cat;
      renderNewsCards(filterItems(state.activeTab));
    });
  });
}

// ── Bottom nav ────────────────────────────────────────────────────────────────

function initNav() {
  $$('.nav-item').forEach(item => {
    item.addEventListener('click', () => {
      const page = item.dataset.page;
      $$('.nav-item').forEach(n => n.classList.remove('active'));
      item.classList.add('active');
      state.activePage = page;

      if (page === 'settings') {
        openSettings();
      } else if (page === 'alerts') {
        state.activeTab = 'all';
        $$('#category-tabs .tab').forEach(t => t.classList.remove('active'));
        $('#category-tabs .tab[data-cat="all"]')?.classList.add('active');
        renderNewsCards(filterItems('all'));
        $('#main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
      } else {
        $('#main-content')?.scrollTo({ top: 0, behavior: 'smooth' });
      }
    });
  });
}

// ── Refresh ───────────────────────────────────────────────────────────────────

async function forceRefresh() {
  showRefreshSpinner(true);
  try {
    await loadAllData();
  } finally {
    showRefreshSpinner(false);
  }
}

function showRefreshSpinner(show) {
  const btn = $('#refresh-btn');
  if (!btn) return;
  btn.style.animation = show ? 'spin 0.8s linear infinite' : '';
}

// ── Pull-to-refresh ───────────────────────────────────────────────────────────

function initPullToRefresh() {
  const main = $('#main-content');
  if (!main) return;

  let startY = 0;
  let pulling = false;
  const THRESHOLD = 70;

  main.addEventListener('touchstart', (e) => {
    if (main.scrollTop === 0) startY = e.touches[0].clientY;
  }, { passive: true });

  main.addEventListener('touchmove', (e) => {
    if (!startY) return;
    const deltaY = e.touches[0].clientY - startY;
    if (deltaY > 20 && main.scrollTop === 0) {
      pulling = true;
      dom.ptrIndicator?.classList.add('visible');
      const progress = Math.min(deltaY / THRESHOLD, 1);
      const span = dom.ptrIndicator?.querySelector('span');
      if (span) span.textContent = progress >= 1 ? 'Release to refresh' : 'Pull to refresh';
    }
  }, { passive: true });

  main.addEventListener('touchend', async () => {
    if (pulling) {
      pulling = false;
      startY  = 0;
      setTimeout(() => dom.ptrIndicator?.classList.remove('visible'), 600);
      await forceRefresh();
    }
    startY = 0;
  });
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(message, duration = 2800) {
  let toast = $('#toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.style.cssText = `
      position: fixed; bottom: calc(80px + var(--safe-bottom, 0px)); left: 50%;
      transform: translateX(-50%) translateY(20px);
      background: #1E293B; color: white;
      padding: 10px 20px; border-radius: 20px;
      font-size: 0.82rem; font-weight: 500;
      z-index: 9999; opacity: 0;
      transition: all 0.25s ease;
      white-space: nowrap;
      box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      max-width: 85vw;
      text-align: center;
      white-space: normal;
    `;
    document.body.appendChild(toast);
  }
  toast.textContent = message;
  toast.style.opacity = '1';
  toast.style.transform = 'translateX(-50%) translateY(0)';
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(10px)';
  }, duration);
}

// ── Header clock ──────────────────────────────────────────────────────────────

function startClock() {
  function tick() {
    if (dom.headerTime) {
      dom.headerTime.innerHTML =
        new Date().toLocaleTimeString('en-IN', {
          hour: '2-digit', minute: '2-digit',
          hour12: true, timeZone: 'Asia/Kolkata',
        }) + '<br><span style="opacity:0.65;font-size:0.65rem">' +
        new Date().toLocaleDateString('en-IN', {
          weekday: 'short', day: 'numeric', month: 'short',
          timeZone: 'Asia/Kolkata',
        }) + '</span>';
    }
    if (state.lastUpdated) updateLastUpdated();
  }
  tick();
  setInterval(tick, 30000);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function setVal(selector, val) {
  const el = $(selector);
  if (el) el.value = val != null ? String(val) : '';
}

function toggleEl(selector, show) {
  const el = $(selector);
  if (el) el.style.display = show ? 'block' : 'none';
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  startClock();
  initTabs();
  initNav();
  initPullToRefresh();
  startLocationTracking();

  // Refresh button
  $('#refresh-btn')?.addEventListener('click', forceRefresh);

  // Settings
  $('#close-settings')?.addEventListener('click', closeSettings);
  dom.settingsOverlay?.addEventListener('click', closeSettings);
  $('#save-settings-btn')?.addEventListener('click', saveSettings);
  $('#refresh-now-btn')?.addEventListener('click', async () => {
    closeSettings();
    await forceRefresh();
  });

  // School board toggle in settings
  $('#s-has-children')?.addEventListener('change', (e) => {
    toggleEl('#s-school-board-group', e.target.checked);
  });

  // Onboarding
  $('#ob-has-children')?.addEventListener('change', (e) => {
    toggleEl('#ob-school-board-group', e.target.checked);
  });
  $('#ob-submit')?.addEventListener('click', submitOnboarding);

  // Check onboarding
  const profile = loadProfile();
  if (profile) {
    state.profile = profile;
    hideOnboarding();
    await loadAllData();
  } else {
    // First launch — show onboarding, don't load yet
    showOnboarding();
  }

  // Online/offline
  window.addEventListener('online', () => {
    state.offline = false;
    dom.offlineBanner?.classList.add('hidden');
    loadAllData();
  });

  window.addEventListener('offline', () => {
    state.offline = true;
    dom.offlineBanner?.classList.remove('hidden');
  });

  // Tab deep-link
  const urlParams    = new URLSearchParams(window.location.search);
  const tabParam     = urlParams.get('tab');
  if (tabParam && tabParam !== 'briefing') {
    const matchingTab = Array.from($$('#category-tabs .tab'))
      .find(t => t.dataset.cat?.toLowerCase().includes(tabParam.toLowerCase()));
    if (matchingTab) matchingTab.click();
  }
}

document.addEventListener('DOMContentLoaded', init);
