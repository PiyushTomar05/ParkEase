/**
 * ParkEase - Smart Parking Management System
 * Frontend Interactions Script
 */

document.addEventListener('DOMContentLoaded', function () {
  'use strict';

  // 1. Auto-dismiss alerts after 5 seconds with pause on hover
  const autoDismissAlerts = document.querySelectorAll('.alert-dismissible');
  autoDismissAlerts.forEach(function (alertEl) {
    let dismissTimer = null;
    const startTimer = function () {
      dismissTimer = setTimeout(function () {
        if (window.bootstrap && bootstrap.Alert) {
          const bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
          if (bsAlert) bsAlert.close();
        } else {
          alertEl.style.transition = 'opacity 0.4s ease';
          alertEl.style.opacity = '0';
          setTimeout(function () {
            alertEl.remove();
          }, 400);
        }
      }, 5000);
    };

    alertEl.addEventListener('mouseenter', function () {
      if (dismissTimer) clearTimeout(dismissTimer);
    });
    alertEl.addEventListener('mouseleave', function () {
      startTimer();
    });

    startTimer();
  });

  // 2. Close mobile navbar when clicking outside or clicking an internal link
  const navCollapse = document.getElementById('navbarMainCollapse');
  const navLinks = document.querySelectorAll('.pe-navbar .nav-link, .pe-navbar .btn');
  if (navCollapse && window.bootstrap && bootstrap.Collapse) {
    const bsCollapse = bootstrap.Collapse.getOrCreateInstance(navCollapse, { toggle: false });
    navLinks.forEach(function (link) {
      link.addEventListener('click', function () {
        if (navCollapse.classList.contains('show')) {
          bsCollapse.hide();
        }
      });
    });
  }

  // 3. Smooth scrolling for hash links
  const anchorLinks = document.querySelectorAll('a[href^="#"]:not([href="#"])');
  anchorLinks.forEach(function (anchor) {
    anchor.addEventListener('click', function (e) {
      const targetId = this.getAttribute('href');
      if (targetId && targetId !== '#') {
        const targetElement = document.querySelector(targetId);
        if (targetElement) {
          e.preventDefault();
          targetElement.scrollIntoView({
            behavior: 'smooth',
            block: 'start'
          });
        }
      }
    });
  });

  // 4. Placeholder notification helper for routes reserved for future phases
  const prototypeLinks = document.querySelectorAll('[data-prototype-notice]');
  prototypeLinks.forEach(function (link) {
    link.addEventListener('click', function (e) {
      const featureName = this.getAttribute('data-prototype-notice') || 'This feature';
      console.info(`[ParkEase Prototype] ${featureName} will be available in the upcoming phase.`);
    });
  });
});
