/**
 * SmartStay – Smart Hostel Management System
 * Interactive Frontend JavaScript Engine
 */

document.addEventListener('DOMContentLoaded', () => {
  initSystemClock();
  initSidebarToggle();
  initNotificationCenter();
  initTableSearch();
  initModals();
  initStarRating();
  initCharts();
});

/* ===================================================================
   1. System Clock
   =================================================================== */
function initSystemClock() {
  const clockEl = document.getElementById('systemClockText');
  if (!clockEl) return;

  function updateClock() {
    const now = new Date();
    const options = { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' };
    clockEl.textContent = now.toLocaleDateString('en-US', options);
  }
  updateClock();
  setInterval(updateClock, 30000);
}

/* ===================================================================
   2. Mobile Sidebar Drawer
   =================================================================== */
function initSidebarToggle() {
  const toggleBtn = document.getElementById('mobileSidebarToggle');
  const sidebar = document.getElementById('appSidebar');

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      sidebar.classList.toggle('show');
    });

    document.addEventListener('click', (e) => {
      if (!sidebar.contains(e.target) && !toggleBtn.contains(e.target)) {
        sidebar.classList.remove('show');
      }
    });
  }
}

/* ===================================================================
   3. Notification Center & AJAX
   =================================================================== */
function initNotificationCenter() {
  const bellBtn = document.getElementById('notificationBellBtn');
  const dropdown = document.getElementById('notificationDropdown');
  const markAllBtn = document.getElementById('markAllReadBtn');
  const badge = document.getElementById('notifBadge');

  if (!bellBtn || !dropdown) return;

  bellBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    dropdown.classList.toggle('show');
  });

  document.addEventListener('click', (e) => {
    if (!dropdown.contains(e.target) && !bellBtn.contains(e.target)) {
      dropdown.classList.remove('show');
    }
  });

  if (markAllBtn) {
    markAllBtn.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/notifications/mark-all-read', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          if (badge) badge.style.display = 'none';
          document.querySelectorAll('.notif-item.unread').forEach(el => el.classList.remove('unread'));
          showToast('All notifications marked as read.', 'success');
        }
      } catch (err) {
        console.error('Error marking notifications read:', err);
      }
    });
  }

  // Click single notification item
  document.querySelectorAll('.notif-item').forEach(item => {
    item.addEventListener('click', async () => {
      const noteId = item.dataset.id;
      const link = item.dataset.link;
      if (noteId && item.classList.contains('unread')) {
        try {
          await fetch(`/api/notifications/mark-read/${noteId}`, { method: 'POST' });
          item.classList.remove('unread');
        } catch (e) {
          console.error(e);
        }
      }
      if (link) window.location.href = link;
    });
  });
}

/* ===================================================================
   4. Live Search Filter for Data Tables
   =================================================================== */
function initTableSearch() {
  const searchInputs = document.querySelectorAll('.table-search-input');
  searchInputs.forEach(input => {
    const tableId = input.dataset.table;
    const table = document.getElementById(tableId);
    if (!table) return;

    input.addEventListener('keyup', () => {
      const filter = input.value.toLowerCase().trim();
      const rows = table.querySelectorAll('tbody tr');

      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (text.includes(filter)) {
          row.style.display = '';
        } else {
          row.style.display = 'none';
        }
      });
    });
  });
}

/* ===================================================================
   5. Modal Dialog Helpers & Form Handlers
   =================================================================== */
function openModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.add('show');
    document.body.style.overflow = 'hidden';
  }
}

function closeModal(modalId) {
  const modal = document.getElementById(modalId);
  if (modal) {
    modal.classList.remove('show');
    document.body.style.overflow = '';
  }
}

function initModals() {
  // Bind close buttons
  document.querySelectorAll('[data-close-modal]').forEach(btn => {
    btn.addEventListener('click', () => {
      const modalId = btn.getAttribute('data-close-modal');
      closeModal(modalId);
    });
  });

  // Close when clicking on backdrop
  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', (e) => {
      if (e.target === backdrop) {
        backdrop.classList.remove('show');
        document.body.style.overflow = '';
      }
    });
  });

  // Outpass Application Form Handler
  const outpassForm = document.getElementById('applyOutpassForm');
  if (outpassForm) {
    outpassForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = outpassForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';

      const formData = new FormData(outpassForm);
      try {
        const res = await fetch('/api/outpass/apply', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'success');
          closeModal('applyOutpassModal');
          setTimeout(() => window.location.reload(), 1000);
        } else {
          showToast(data.message || 'Submission failed.', 'danger');
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Application';
        }
      } catch (err) {
        showToast('Server error while submitting outpass.', 'danger');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> Submit Application';
      }
    });
  }

  // Digital Outpass Viewer Trigger
  document.querySelectorAll('.btn-view-digital-pass').forEach(btn => {
    btn.addEventListener('click', async () => {
      const outpassId = btn.dataset.id;
      if (!outpassId) return;

      try {
        const res = await fetch(`/api/outpass/${outpassId}/details`);
        if (!res.ok) throw new Error('Failed to load pass details');
        const pass = await res.json();

        // Populate pass modal fields
        document.getElementById('passStudentName').textContent = pass.student_name;
        document.getElementById('passRollNo').textContent = pass.roll_no;
        document.getElementById('passRoomBlock').textContent = `${pass.block_name} • Room ${pass.room_number}`;
        document.getElementById('passCodeDisplay').textContent = pass.pass_code;
        document.getElementById('passDeparture').textContent = pass.departure;
        document.getElementById('passReturn').textContent = pass.return_schedule;
        document.getElementById('passDestination').textContent = pass.destination;
        document.getElementById('passReason').textContent = pass.reason;
        document.getElementById('passApprovedBy').textContent = pass.approved_by;
        
        // Status badge & stamp
        const stamp = document.getElementById('passStamp');
        if (stamp) {
          stamp.textContent = pass.status.toUpperCase();
          if (pass.status === 'Approved') {
            stamp.style.color = '#059669';
            stamp.style.borderColor = '#059669';
            stamp.style.background = '#ecfdf5';
          } else if (pass.status === 'Completed') {
            stamp.style.color = '#0284c7';
            stamp.style.borderColor = '#0284c7';
            stamp.style.background = '#f0f9ff';
          } else if (pass.status === 'Pending') {
            stamp.style.color = '#d97706';
            stamp.style.borderColor = '#d97706';
            stamp.style.background = '#fffbeb';
          } else {
            stamp.style.color = '#e11d48';
            stamp.style.borderColor = '#e11d48';
            stamp.style.background = '#fff1f2';
          }
        }

        // Generate QR Code on canvas
        renderQrPattern('passQrCanvas', pass.pass_code);

        openModal('digitalPassModal');
      } catch (err) {
        showToast('Unable to load outpass details.', 'danger');
      }
    });
  });

  // Complaint Submit Form Handler
  const complaintForm = document.getElementById('submitComplaintForm');
  if (complaintForm) {
    complaintForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submitBtn = complaintForm.querySelector('button[type="submit"]');
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting...';

      const formData = new FormData(complaintForm);
      try {
        const res = await fetch('/api/complaints/submit', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'success');
          closeModal('newComplaintModal');
          setTimeout(() => window.location.reload(), 1000);
        } else {
          showToast(data.message || 'Error registering complaint.', 'danger');
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> File Ticket';
        }
      } catch (err) {
        showToast('Network error while filing complaint.', 'danger');
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-paper-plane"></i> File Ticket';
      }
    });
  }

  // Announcement Create Form Handler
  const announcementForm = document.getElementById('createAnnouncementForm');
  if (announcementForm) {
    announcementForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(announcementForm);
      try {
        const res = await fetch('/api/announcements/create', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'success');
          closeModal('newAnnouncementModal');
          setTimeout(() => window.location.reload(), 800);
        } else {
          showToast(data.message, 'danger');
        }
      } catch (e) {
        showToast('Error creating announcement.', 'danger');
      }
    });
  }
}

/* ===================================================================
   6. Outpass Warden Actions (Approve / Reject / Complete)
   =================================================================== */
async function handleOutpassAction(outpassId, action, remarks = '') {
  const formData = new FormData();
  formData.append('action', action);
  formData.append('remarks', remarks);

  try {
    const res = await fetch(`/api/outpass/${outpassId}/action`, { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.message || 'Action failed.', 'danger');
    }
  } catch (err) {
    showToast('Failed to communicate with server.', 'danger');
  }
}

async function markOutpassCompleted(outpassId) {
  if (!confirm('Confirm student return and mark this outpass Completed?')) return;
  try {
    const res = await fetch(`/api/outpass/${outpassId}/complete`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.message, 'danger');
    }
  } catch (err) {
    showToast('Error marking outpass completed.', 'danger');
  }
}

function openRejectOutpassModal(outpassId, passCode) {
  const idInput = document.getElementById('rejectOutpassId');
  const codeSpan = document.getElementById('rejectPassCode');
  if (idInput && codeSpan) {
    idInput.value = outpassId;
    codeSpan.textContent = passCode;
    openModal('rejectOutpassModal');
  }
}

// Confirm Reject submit
const rejectForm = document.getElementById('rejectOutpassForm');
if (rejectForm) {
  rejectForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const outpassId = document.getElementById('rejectOutpassId').value;
    const remarks = document.getElementById('rejectRemarks').value.trim();
    if (!remarks) {
      showToast('Please enter a rejection reason.', 'warning');
      return;
    }
    handleOutpassAction(outpassId, 'reject', remarks);
    closeModal('rejectOutpassModal');
  });
}

/* ===================================================================
   7. Complaint Resolution Actions
   =================================================================== */
function openComplaintStatusModal(complaintId, ticketNumber, currentStatus) {
  const idInput = document.getElementById('resolveComplaintId');
  const ticketSpan = document.getElementById('resolveTicketNumber');
  const statusSelect = document.getElementById('resolveStatusSelect');

  if (idInput && ticketSpan && statusSelect) {
    idInput.value = complaintId;
    ticketSpan.textContent = ticketNumber;
    statusSelect.value = currentStatus;
    openModal('resolveComplaintModal');
  }
}

const resolveComplaintForm = document.getElementById('resolveComplaintForm');
if (resolveComplaintForm) {
  resolveComplaintForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('resolveComplaintId').value;
    const formData = new FormData(resolveComplaintForm);

    try {
      const res = await fetch(`/api/complaints/${id}/status`, { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeModal('resolveComplaintModal');
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(data.message, 'danger');
      }
    } catch (err) {
      showToast('Failed to update complaint.', 'danger');
    }
  });
}

/* ===================================================================
   8. Food Menu Admin Edit & Feedback Ratings
   =================================================================== */
function openEditMenuModal(day, mealType, items, timings, note) {
  document.getElementById('menuDayOfWeek').value = day;
  document.getElementById('menuMealType').value = mealType;
  document.getElementById('menuItemsInput').value = items;
  document.getElementById('menuTimingsInput').value = timings;
  document.getElementById('menuSpecialNoteInput').value = note || '';
  openModal('editMenuModal');
}

const editMenuForm = document.getElementById('editMenuForm');
if (editMenuForm) {
  editMenuForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(editMenuForm);
    try {
      const res = await fetch('/api/food-menu/update', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeModal('editMenuModal');
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(data.message, 'danger');
      }
    } catch (e) {
      showToast('Failed to update food menu.', 'danger');
    }
  });
}

function initStarRating() {
  const container = document.getElementById('foodRatingStars');
  if (!container) return;

  const stars = container.querySelectorAll('.fa-star');
  const ratingInput = document.getElementById('feedbackRatingValue');

  stars.forEach(star => {
    star.addEventListener('click', () => {
      const val = parseInt(star.dataset.val, 10);
      if (ratingInput) ratingInput.value = val;

      stars.forEach(s => {
        const sVal = parseInt(s.dataset.val, 10);
        if (sVal <= val) {
          s.classList.add('active');
        } else {
          s.classList.remove('active');
        }
      });
    });
  });

  const feedbackForm = document.getElementById('submitFoodFeedbackForm');
  if (feedbackForm) {
    feedbackForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const formData = new FormData(feedbackForm);
      try {
        const res = await fetch('/api/food-menu/feedback', { method: 'POST', body: formData });
        const data = await res.json();
        if (data.success) {
          showToast(data.message, 'success');
          feedbackForm.reset();
          stars.forEach(s => s.classList.add('active')); // Reset to 5
          if (ratingInput) ratingInput.value = 5;
        } else {
          showToast(data.message, 'danger');
        }
      } catch (e) {
        showToast('Error recording food feedback.', 'danger');
      }
    });
  }
}

/* ===================================================================
   9. Room Allocation & Management Actions
   =================================================================== */
function openAllocateModal(studentId, studentName, rollNo) {
  document.getElementById('allocStudentId').value = studentId;
  document.getElementById('allocStudentName').textContent = `${studentName} (${rollNo})`;
  openModal('allocateRoomModal');
}

const allocateForm = document.getElementById('allocateRoomForm');
if (allocateForm) {
  allocateForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(allocateForm);
    try {
      const res = await fetch('/api/rooms/allocate', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeModal('allocateRoomModal');
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(data.message, 'danger');
      }
    } catch (e) {
      showToast('Error allocating room.', 'danger');
    }
  });
}

async function deallocateRoom(studentId, studentName) {
  if (!confirm(`Are you sure you want to remove ${studentName} from their allocated room?`)) return;
  const formData = new FormData();
  formData.append('student_id', studentId);
  try {
    const res = await fetch('/api/rooms/deallocate', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.message, 'danger');
    }
  } catch (e) {
    showToast('Failed to deallocate room.', 'danger');
  }
}

const addRoomForm = document.getElementById('addRoomForm');
if (addRoomForm) {
  addRoomForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(addRoomForm);
    try {
      const res = await fetch('/api/rooms/add', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeModal('addRoomModal');
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(data.message, 'danger');
      }
    } catch (e) {
      showToast('Error adding room.', 'danger');
    }
  });
}

/* ===================================================================
   10. Admin User Management (Wardens, Deletion)
   =================================================================== */
const addWardenForm = document.getElementById('addWardenForm');
if (addWardenForm) {
  addWardenForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData(addWardenForm);
    try {
      const res = await fetch('/api/admin/users/add-warden', { method: 'POST', body: formData });
      const data = await res.json();
      if (data.success) {
        showToast(data.message, 'success');
        closeModal('addWardenModal');
        setTimeout(() => window.location.reload(), 800);
      } else {
        showToast(data.message, 'danger');
      }
    } catch (e) {
      showToast('Error adding warden.', 'danger');
    }
  });
}

async function deleteUser(userId, userName) {
  if (!confirm(`Delete user account "${userName}" permanently? This cannot be undone.`)) return;
  try {
    const res = await fetch(`/api/admin/users/delete-user/${userId}`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      showToast(data.message, 'success');
      setTimeout(() => window.location.reload(), 800);
    } else {
      showToast(data.message, 'danger');
    }
  } catch (e) {
    showToast('Error deleting user.', 'danger');
  }
}

/* ===================================================================
   11. Chart.js Dashboard Visualizations
   =================================================================== */
async function initCharts() {
  const hasOutpassChart = document.getElementById('outpassDistributionChart');
  const hasComplaintsChart = document.getElementById('complaintsCategoryChart');
  const hasOccupancyChart = document.getElementById('blockOccupancyChart');
  const hasWeeklyChart = document.getElementById('weeklyOutpassesChart');

  if (!hasOutpassChart && !hasComplaintsChart && !hasOccupancyChart && !hasWeeklyChart) {
    return;
  }

  try {
    const res = await fetch('/api/analytics/charts');
    if (!res.ok) return;
    const chartsData = await res.json();

    // Chart 1: Outpass Distribution (Doughnut)
    if (hasOutpassChart) {
      new Chart(hasOutpassChart, {
        type: 'doughnut',
        data: {
          labels: chartsData.outpass_distribution.labels,
          datasets: [{
            data: chartsData.outpass_distribution.data,
            backgroundColor: ['#f59e0b', '#10b981', '#f43f5e', '#0ea5e9'],
            borderWidth: 2,
            borderColor: '#ffffff'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { position: 'bottom', labels: { boxWidth: 12, font: { family: 'Plus Jakarta Sans', weight: '600' } } }
          },
          cutout: '68%'
        }
      });
    }

    // Chart 2: Complaints by Category (Bar)
    if (hasComplaintsChart) {
      new Chart(hasComplaintsChart, {
        type: 'bar',
        data: {
          labels: chartsData.complaints_category.labels,
          datasets: [{
            label: 'Tickets',
            data: chartsData.complaints_category.data,
            backgroundColor: '#7c3aed',
            borderRadius: 6
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 } },
            x: { grid: { display: false } }
          }
        }
      });
    }

    // Chart 3: Block Occupancy vs Capacity (Bar)
    if (hasOccupancyChart) {
      new Chart(hasOccupancyChart, {
        type: 'bar',
        data: {
          labels: chartsData.block_occupancy.labels,
          datasets: [
            {
              label: 'Occupied Beds',
              data: chartsData.block_occupancy.occupied,
              backgroundColor: '#6366f1',
              borderRadius: 6
            },
            {
              label: 'Total Capacity',
              data: chartsData.block_occupancy.capacity,
              backgroundColor: '#e2e8f0',
              borderRadius: 6
            }
          ]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom' } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 } },
            x: { grid: { display: false } }
          }
        }
      });
    }

    // Chart 4: Weekly Outpasses Trend (Line)
    if (hasWeeklyChart) {
      new Chart(hasWeeklyChart, {
        type: 'line',
        data: {
          labels: chartsData.weekly_outpasses.labels,
          datasets: [{
            label: 'Outpass Requests',
            data: chartsData.weekly_outpasses.data,
            borderColor: '#7c3aed',
            backgroundColor: 'rgba(124, 58, 237, 0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 3,
            pointBackgroundColor: '#7c3aed',
            pointRadius: 4
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            y: { beginAtZero: true, ticks: { precision: 0 } },
            x: { grid: { display: false } }
          }
        }
      });
    }

  } catch (err) {
    console.warn('Charts could not be loaded:', err);
  }
}

/* ===================================================================
   12. QR Code Pattern Drawer (Canvas Vector Generator)
   =================================================================== */
function renderQrPattern(canvasId, text) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const size = canvas.width;
  ctx.clearRect(0, 0, size, size);

  // Background
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, size, size);

  // Hash-based deterministic QR-like grid
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = (hash << 5) - hash + text.charCodeAt(i);
    hash |= 0;
  }

  const cells = 15;
  const cellSize = size / cells;
  ctx.fillStyle = '#0f172a';

  // Corner finder markers
  function drawFinder(startX, startY) {
    ctx.fillRect(startX * cellSize, startY * cellSize, 4 * cellSize, 4 * cellSize);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect((startX + 1) * cellSize, (startY + 1) * cellSize, 2 * cellSize, 2 * cellSize);
    ctx.fillStyle = '#7c3aed';
    ctx.fillRect((startX + 1.3) * cellSize, (startY + 1.3) * cellSize, 1.4 * cellSize, 1.4 * cellSize);
    ctx.fillStyle = '#0f172a';
  }

  drawFinder(0, 0);
  drawFinder(cells - 4, 0);
  drawFinder(0, cells - 4);

  // Interior data pseudo-matrix
  let seed = Math.abs(hash);
  for (let r = 0; r < cells; r++) {
    for (let c = 0; c < cells; c++) {
      // Skip finder corners
      if ((r < 5 && c < 5) || (r < 5 && c >= cells - 5) || (r >= cells - 5 && c < 5)) continue;
      seed = (seed * 9301 + 49297) % 233280;
      if (seed / 233280 > 0.45) {
        ctx.fillRect(c * cellSize + 0.5, r * cellSize + 0.5, cellSize - 1, cellSize - 1);
      }
    }
  }
}

/* ===================================================================
   13. Toast Notification Utility
   =================================================================== */
function showToast(message, type = 'info') {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  let icon = 'fa-info-circle';
  if (type === 'success') icon = 'fa-circle-check';
  if (type === 'danger') icon = 'fa-triangle-exclamation';
  if (type === 'warning') icon = 'fa-bell';

  toast.innerHTML = `
    <i class="fa-solid ${icon}" style="font-size: 1.1rem; color: var(--${type === 'success' ? 'emerald' : type === 'danger' ? 'rose' : type === 'warning' ? 'amber' : 'purple'}-600)"></i>
    <div style="flex: 1; font-size: 0.86rem; font-weight: 500; color: var(--navy-900);">${message}</div>
    <button style="background: none; border: none; cursor: pointer; color: var(--text-muted);" onclick="this.parentElement.remove()">
      <i class="fa-solid fa-xmark"></i>
    </button>
  `;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Print Gate Pass helper
function printDigitalPass() {
  window.print();
}
