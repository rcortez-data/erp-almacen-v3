from django.test import TestCase
class AccountTests(TestCase):
    def test_registration_hashes_password(self):
        response=self.client.post("/cuenta/registro/",{"username":"cliente","first_name":"Ana","last_name":"Demo","email":"ana@example.com","password1":"Clave-segura-456!","password2":"Clave-segura-456!"})
        self.assertRedirects(response,"/cuenta/perfil/"); from django.contrib.auth.models import User; self.assertTrue(User.objects.get(username="cliente").check_password("Clave-segura-456!"))
