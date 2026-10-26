package com.tourist.safety

import android.app.AlertDialog
import android.content.Context
import android.view.LayoutInflater
import android.widget.*
import androidx.lifecycle.LifecycleCoroutineScope
import kotlinx.coroutines.*

/**
 * RegistrationDialog — collects Aadhaar/passport, calls backend /register.
 * Implements: Requirements 2.1, 2.2, 2.3
 */
class RegistrationDialog(
    private val context: Context,
    private val onSuccess: (touristId: String, validUntil: Long, txHash: String?) -> Unit
) {
    fun show() {
        val layout = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 32, 48, 16)
        }

        val etName = EditText(context).apply { hint = "Your full name" }
        val spinnerLabel = TextView(context).apply { text = "ID Type" }
        val spinner = Spinner(context).apply {
            adapter = ArrayAdapter(context, android.R.layout.simple_spinner_item,
                listOf("Aadhaar", "Passport")).also {
                it.setDropDownViewResource(android.R.layout.simple_spinner_dropdown_item)
            }
        }
        val etIdValue = EditText(context).apply { hint = "Enter Aadhaar / Passport number" }
        val etVisitEnd = EditText(context).apply { hint = "Visit end (days from today, e.g. 7)" }
        val tvStatus = TextView(context).apply { text = "" }

        layout.addView(etName)
        layout.addView(spinnerLabel)
        layout.addView(spinner)
        layout.addView(etIdValue)
        layout.addView(etVisitEnd)
        layout.addView(tvStatus)

        AlertDialog.Builder(context)
            .setTitle("Register — Maharashtra Tourist ID")
            .setView(layout)
            .setPositiveButton("Register") { _, _ ->
                val name = etName.text.toString().trim()
                val idType = if (spinner.selectedItemPosition == 0) "aadhaar" else "passport"
                val idValue = etIdValue.text.toString().trim()
                val days = etVisitEnd.text.toString().toLongOrNull() ?: 7L
                val now = System.currentTimeMillis()
                val visitEnd = now + days * 24 * 60 * 60 * 1000L

                if (name.isEmpty()) {
                    Toast.makeText(context, "Please enter your name", Toast.LENGTH_SHORT).show()
                    return@setPositiveButton
                }

                CoroutineScope(Dispatchers.Main).launch {
                    tvStatus.text = "Registering…"
                    try {
                        val resp = withContext(Dispatchers.IO) {
                            ApiClient.api.register(
                                RegistrationRequest(idType, idValue, now, visitEnd, name = name)
                            )
                        }
                        if (resp.isSuccessful) {
                            resp.body()?.let { body ->
                                // Save JWT token and name for authenticated calls
                                body.token?.let { TouristPreferences.saveJwt(context, it) }
                                TouristPreferences.saveName(context, name)
                                onSuccess(body.touristId, body.validUntil, body.txHash)
                                Toast.makeText(context, "Registered: ${body.touristId}", Toast.LENGTH_LONG).show()
                            }
                        } else {
                            Toast.makeText(context, "Registration failed: ${resp.code()}", Toast.LENGTH_LONG).show()
                        }
                    } catch (e: Exception) {
                        Toast.makeText(context, "Network error: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }
            .setNegativeButton("Cancel", null)
            .show()
    }
}
